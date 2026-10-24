"""Fetch small excerpts from Python's official documentation only."""

from __future__ import annotations

from html.parser import HTMLParser
import builtins
import hashlib
import os
import sys
import sysconfig
from importlib.machinery import PathFinder
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from agent.models import DocumentationEvidence


DOCS_BASE = "https://docs.python.org/3"
_BUILTIN_FUNCTIONS = f"{DOCS_BASE}/library/functions.html"
_BUILTIN_TYPES = f"{DOCS_BASE}/library/stdtypes.html"


class _DefinitionExtractor(HTMLParser):
    """Read the definition-list item following a matching documentation anchor."""

    def __init__(self, anchor: str) -> None:
        super().__init__(convert_charrefs=True)
        self.anchor = anchor
        self.found = False
        self.matched = False
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if not self.found and attributes.get("id") == self.anchor:
            self.found = True
            self.matched = True
        elif self.found and self.depth == 0 and tag == "dt":
            self.found = False
        if self.found and tag == "dd":
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.found and tag == "dd" and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.found and self.depth and data.strip():
            self.parts.append(" ".join(data.split()))


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


def is_documentable(module: str, symbol: str) -> bool:
    """Return whether a target maps to a supported official Python docs page."""
    return _official_doc_url(module, symbol) is not None


def _source_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"source-{digest}"


def _title(module: str, symbol: str) -> str:
    return f"Python documentation: {module}.{symbol}"


def lookup_documentation(module: str, symbol: str) -> DocumentationEvidence:
    """Return an official Python documentation excerpt and URL for a target."""
    resolved = _official_doc_url(module, symbol)
    if resolved is None:
        return DocumentationEvidence(
            source_id="",
            status="unsupported",
            module=module,
            symbol=symbol,
            title="",
            excerpt="이 대상은 지원하는 Python 내장 함수 또는 표준 라이브러리로 확인되지 않았습니다.",
            url="",
        )

    url, anchor = resolved
    page_url = url.split("#", 1)[0]
    source_id = _source_id(url)
    title = _title(module, symbol)
    try:
        request = Request(page_url, headers={"User-Agent": "AI-Code-Decoder/1.0"})
        with urlopen(request, timeout=6) as response:
            html = response.read(1_500_000).decode("utf-8", errors="replace")
        extractor = _DefinitionExtractor(anchor)
        extractor.feed(html)
        excerpt = " ".join(extractor.parts)
        if extractor.matched and excerpt:
            return DocumentationEvidence(
                source_id=source_id,
                status="exact_match",
                module=module,
                symbol=symbol,
                title=title,
                excerpt=excerpt[:2_000],
                url=url,
            )
        return DocumentationEvidence(
            source_id=source_id,
            status="page_only",
            module=module,
            symbol=symbol,
            title=title,
            excerpt="공식 문서 페이지는 확인했지만 해당 심볼의 발췌를 찾지 못했습니다.",
            url=page_url,
        )
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError) as exc:
        return DocumentationEvidence(
            source_id=source_id,
            status="unavailable",
            module=module,
            symbol=symbol,
            title=title,
            excerpt=f"공식 문서를 지금 가져오지 못했습니다 ({type(exc).__name__}). URL을 확인해 주세요.",
            url=url,
            error_type=type(exc).__name__,
        )
