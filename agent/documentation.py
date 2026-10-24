"""Fetch small excerpts from official documentation.

Built-ins and the standard library use docs.python.org. Packages registered in
`agent.package_registry` use their own docs site. Any other package is reported
as unsupported without a network request.
"""

from __future__ import annotations

import builtins
import hashlib
import os
import re
import sys
import sysconfig
import zlib
from functools import lru_cache
from html.parser import HTMLParser
from importlib.machinery import PathFinder
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from agent.models import DocumentationEvidence
from agent.package_registry import PackageDocs, registered_package

DOCS_BASE = "https://docs.python.org/3"
_BUILTIN_FUNCTIONS = f"{DOCS_BASE}/library/functions.html"
_BUILTIN_TYPES = f"{DOCS_BASE}/library/stdtypes.html"
_FETCH_TIMEOUT_SECONDS = 6
_MAX_PAGE_BYTES = 1_500_000
_MAX_INVENTORY_BYTES = 3_000_000
# Upper bound for a decompressed inventory, so a hostile file cannot exhaust memory.
_MAX_INVENTORY_TEXT_BYTES = 30_000_000
_MAX_EXCERPT_CHARS = 2_000
_INVENTORY_LINE = re.compile(r"(.+?)\s+(\S+)\s+(-?\d+)\s+?(\S*)\s+(.*)")
_LLMS_LINK = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)\s]+)\)\s*$")


class _IndexFormatError(ValueError):
    """Raised when a downloaded symbol index is not in the expected format."""


# zlib.error covers corrupt inventories.
_FETCH_ERRORS = (
    HTTPError,
    URLError,
    TimeoutError,
    OSError,
    UnicodeError,
    zlib.error,
    _IndexFormatError,
)


class _LlmsEntry(NamedTuple):
    url: str
    description: str


class _DefinitionExtractor(HTMLParser):
    """Read the definition-list item following a matching documentation anchor."""

    def __init__(self, anchor: str) -> None:
        super().__init__(convert_charrefs=True)
        self.anchor = anchor
        self.found = False
        self.matched = False
        self.has_definition = False
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if not self.found and attributes.get("id") == self.anchor:
            self.found = True
            self.matched = True
        # Overloaded APIs list several signature <dt>s before one shared <dd>.
        elif self.found and self.depth == 0 and tag == "dt" and self.has_definition:
            self.found = False
        if self.found and tag == "dd":
            self.depth += 1
            self.has_definition = True

    def handle_endtag(self, tag: str) -> None:
        if self.found and tag == "dd" and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.found and self.depth and data.strip():
            self.parts.append(" ".join(data.split()))


class _DocContentsExtractor(HTMLParser):
    """Read the mkdocstrings `doc-contents` block following a matching heading."""

    def __init__(self, anchor: str) -> None:
        super().__init__(convert_charrefs=True)
        self.anchor = anchor
        self.matched = False
        self.done = False
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        attributes = dict(attrs)
        if not self.matched:
            self.matched = attributes.get("id") == self.anchor
            return
        if tag != "div":
            return
        if self.depth:
            self.depth += 1
        elif "doc-contents" in (attributes.get("class") or "").split():
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.depth:
            self.depth -= 1
            self.done = not self.depth

    def handle_data(self, data: str) -> None:
        if self.depth and data.strip():
            self.parts.append(" ".join(data.split()))


class _SectionExtractor(HTMLParser):
    """Read the text between a matching heading and the next heading."""

    _HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
    _HIDDEN = frozenset({"script", "style", "svg"})

    def __init__(self, anchor: str) -> None:
        super().__init__(convert_charrefs=True)
        self.anchor = anchor
        self.in_heading = False
        self.collecting = False
        self.done = False
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._HIDDEN:
            self.hidden_depth += 1
        if self.done or tag not in self._HEADINGS:
            return
        if self.collecting:
            self.done = True
        elif dict(attrs).get("id") == self.anchor:
            self.in_heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._HIDDEN and self.hidden_depth:
            self.hidden_depth -= 1
        if self.in_heading and tag in self._HEADINGS:
            self.in_heading = False
            self.collecting = True

    def handle_data(self, data: str) -> None:
        if self.collecting and not self.done and not self.hidden_depth and data.strip():
            self.parts.append(" ".join(data.split()))


def _extract_definition(html: str, anchor: str) -> tuple[bool, str]:
    """Return whether the anchor exists and the text documenting it."""
    # mkdocstrings pages are recognized by their doc-contents block; Sphinx pages
    # never have one, so they fall through to the definition-list extractor.
    doc_contents = _DocContentsExtractor(anchor)
    doc_contents.feed(html)
    if doc_contents.parts:
        return True, " ".join(doc_contents.parts)
    definition = _DefinitionExtractor(anchor)
    definition.feed(html)
    if definition.parts:
        return True, " ".join(definition.parts)
    # Other generators (e.g. Starlight) put the description after a plain heading.
    section = _SectionExtractor(anchor)
    section.feed(html)
    return definition.matched, " ".join(section.parts)


def _official_doc_url(module: str, symbol: str) -> tuple[str, str] | None:
    module = module.strip()
    symbol = symbol.strip()
    if not symbol:
        return None

    builtin_names = set(dir(builtins))
    if module in {"builtins", "__builtin__"}:
        if symbol.split(".", 1)[0] not in builtin_names:
            return None
        page = _BUILTIN_FUNCTIONS if "." not in symbol else _BUILTIN_TYPES
        anchor = symbol
        return f"{page}#{quote(anchor, safe='._-')}", anchor

    root_module = module.split(".", 1)[0]
    if not _is_standard_library(root_module):
        return None

    page = f"{DOCS_BASE}/library/{quote(module, safe='._-')}.html"
    anchor = symbol if symbol.startswith(module + ".") else f"{module}.{symbol}"
    return f"{page}#{quote(anchor, safe='._-')}", anchor


def _is_standard_library(module: str) -> bool:
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return module in names
    if module in sys.builtin_module_names:
        return True

    # Python 3.9 does not expose stdlib_module_names. Resolve the top-level
    # module without importing it, then ensure it lives under the stdlib path.
    spec = PathFinder.find_spec(module, sys.path)
    origin = getattr(spec, "origin", None)
    if not origin or origin in {"built-in", "frozen"}:
        return False
    stdlib_path = os.path.realpath(sysconfig.get_path("stdlib"))
    origin_path = os.path.realpath(origin)
    try:
        under_stdlib = os.path.commonpath([stdlib_path, origin_path]) == stdlib_path
    except ValueError:
        return False
    return under_stdlib and "site-packages" not in origin_path and "dist-packages" not in origin_path


def _source_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"source-{digest}"


def _title(project: str, module: str, symbol: str) -> str:
    return f"{project} documentation: {module}.{symbol}"


def _download(url: str, limit: int) -> bytes:
    request = Request(url, headers={"User-Agent": "AI-Code-Decoder/1.0"})
    with urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        return response.read(limit)


# Cache per page so same-page symbols share one download; failures raise and are never cached.
@lru_cache(maxsize=16)
def _fetch_page(page_url: str) -> str:
    return _download(page_url, _MAX_PAGE_BYTES).decode("utf-8", errors="replace")


@lru_cache(maxsize=8)
def _fetch_inventory(index_url: str) -> dict[str, str]:
    """Map Python object names to documentation URIs from a Sphinx objects.inv file."""
    header = _download(index_url, _MAX_INVENTORY_BYTES).split(b"\n", 4)
    if len(header) < 5 or not header[0].startswith(b"# Sphinx inventory version 2"):
        raise _IndexFormatError("unsupported inventory format")
    compressed = header[4]
    body = zlib.decompressobj().decompress(compressed, _MAX_INVENTORY_TEXT_BYTES).decode("utf-8")
    inventory: dict[str, str] = {}
    for line in body.splitlines():
        match = _INVENTORY_LINE.fullmatch(line)
        if not match:
            continue
        name, role, _, uri, _ = match.groups()
        if role.startswith("py:"):
            inventory.setdefault(name, uri.replace("$", name) if uri.endswith("$") else uri)
    return inventory


@lru_cache(maxsize=4)
def _fetch_llms_index(index_url: str) -> dict[str, _LlmsEntry]:
    """Map names to their page URL and one-line description from an llms.txt link list."""
    lines = _fetch_page(index_url).splitlines()
    index: dict[str, _LlmsEntry] = {}
    for position, line in enumerate(lines):
        match = _LLMS_LINK.match(line)
        if not match:
            continue
        following = lines[position + 1].strip() if position + 1 < len(lines) else ""
        description = "" if following.startswith(("-", "#")) else following
        index.setdefault(
            match.group(1), _LlmsEntry(urljoin(index_url, match.group(2)), description)
        )
    return index


def _inventory_url(
    package: PackageDocs, inventory: dict[str, str], module: str, symbol: str
) -> str | None:
    uri = inventory.get(f"{module}.{symbol}")
    if uri is None:
        # Packages re-export names from submodules: pydantic.BaseModel is documented
        # as pydantic.main.BaseModel. Accept only one unambiguous candidate.
        candidates = [
            name
            for name in inventory
            if name.startswith(f"{module}.") and name.endswith(f".{symbol}")
        ]
        if len(candidates) != 1:
            return None
        uri = inventory[candidates[0]]
    return urljoin(package.docs_url, uri)


def _llms_name(package: PackageDocs, module: str, symbol: str) -> str:
    root = module.split(".", 1)[0]
    return package.index_root + f"{module}.{symbol}"[len(root) :]


def _unavailable(
    module: str, symbol: str, title: str, url: str, exc: Exception
) -> DocumentationEvidence:
    return DocumentationEvidence(
        source_id=_source_id(url),
        status="unavailable",
        module=module,
        symbol=symbol,
        title=title,
        excerpt=(
            f"공식 문서를 지금 가져오지 못했습니다 ({type(exc).__name__}). URL을 확인해 주세요."
        ),
        url=url,
        error_type=type(exc).__name__,
    )


def _page_only(
    module: str, symbol: str, title: str, url: str, excerpt: str
) -> DocumentationEvidence:
    return DocumentationEvidence(
        source_id=_source_id(url),
        status="page_only",
        module=module,
        symbol=symbol,
        title=title,
        excerpt=excerpt,
        url=url,
    )


def _exact_match(
    module: str, symbol: str, title: str, url: str, excerpt: str
) -> DocumentationEvidence:
    return DocumentationEvidence(
        source_id=_source_id(url),
        status="exact_match",
        module=module,
        symbol=symbol,
        title=title,
        excerpt=excerpt[:_MAX_EXCERPT_CHARS],
        url=url,
    )


def _page_evidence(module: str, symbol: str, title: str, url: str) -> DocumentationEvidence:
    """Fetch the page behind `url` and cite it only when its anchor has a definition."""
    page_url, _, anchor = url.partition("#")
    try:
        is_anchor_found, excerpt = _extract_definition(_fetch_page(page_url), anchor)
    except _FETCH_ERRORS as exc:
        return _unavailable(module, symbol, title, url, exc)
    if is_anchor_found and excerpt:
        return _exact_match(module, symbol, title, url, excerpt)
    return _page_only(
        module,
        symbol,
        title,
        page_url,
        "공식 문서 페이지는 확인했지만 해당 심볼의 발췌를 찾지 못했습니다.",
    )


def _not_indexed(
    package: PackageDocs, module: str, symbol: str, title: str
) -> DocumentationEvidence:
    return _page_only(
        module,
        symbol,
        title,
        package.docs_url,
        f"{package.project} 공식 문서 색인에서 해당 심볼을 찾지 못했습니다.",
    )


def _inventory_evidence(
    package: PackageDocs, module: str, symbol: str, title: str
) -> DocumentationEvidence:
    try:
        inventory = _fetch_inventory(package.index_url)
    except _FETCH_ERRORS as exc:
        return _unavailable(module, symbol, title, package.docs_url, exc)
    url = _inventory_url(package, inventory, module, symbol)
    if url is None:
        return _not_indexed(package, module, symbol, title)
    return _page_evidence(module, symbol, title, url)


def _llms_evidence(
    package: PackageDocs, module: str, symbol: str, title: str
) -> DocumentationEvidence:
    try:
        index = _fetch_llms_index(package.index_url)
    except _FETCH_ERRORS as exc:
        return _unavailable(module, symbol, title, package.docs_url, exc)
    name = _llms_name(package, module, symbol)
    entry = index.get(name)
    if entry and entry.description:
        return _exact_match(module, symbol, title, entry.url, entry.description)
    # Point at the closest documented parent (st.column_config for
    # st.column_config.TextColumn), but never cite it as this symbol.
    while not entry and "." in name:
        name = name.rsplit(".", 1)[0]
        entry = index.get(name)
    if entry is None or name == package.index_root:
        return _not_indexed(package, module, symbol, title)
    return _page_only(
        module,
        symbol,
        title,
        entry.url,
        f"`{name}` 공식 문서 페이지에서 해당 심볼을 확인해 주세요.",
    )


def _package_evidence(package: PackageDocs, module: str, symbol: str) -> DocumentationEvidence:
    """Resolve a registered third-party symbol through its package's own docs index."""
    title = _title(package.project, module, symbol)
    if package.index_kind == "llms_txt":
        return _llms_evidence(package, module, symbol, title)
    return _inventory_evidence(package, module, symbol, title)


def lookup_documentation(module: str, symbol: str) -> DocumentationEvidence:
    """Return an official documentation excerpt and URL for a target."""
    resolved = _official_doc_url(module, symbol)
    if resolved is not None:
        return _page_evidence(module, symbol, _title("Python", module, symbol), resolved[0])

    package = registered_package(module.strip())
    if package is not None and symbol.strip():
        return _package_evidence(package, module.strip(), symbol.strip())

    return DocumentationEvidence(
        source_id="",
        status="unsupported",
        module=module,
        symbol=symbol,
        title="",
        excerpt=(
            "이 대상은 Python 내장 기능, 표준 라이브러리, 등록된 서드파티 패키지의 "
            "공식 문서로 확인되지 않았습니다."
        ),
        url="",
    )
