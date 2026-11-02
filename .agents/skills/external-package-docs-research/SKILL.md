---
name: external-package-docs-research
description: Research official documentation for a third-party Python package when evaluating whether AI Code Decode should explain that package, support its API references, or add it to the package registry (`agent/package_registry.py`).
---

# External Package Documentation Research

Use this skill to investigate a request to add or evaluate third-party Python package documentation support. Research findings alone do not change the app's current support boundary.

1. Identify the package, version range, symbols, and user-facing behavior the request needs. If details are missing, make a narrow research assumption and state it.
2. Search the package's official documentation and, when relevant, official release notes or API reference. Prefer primary sources; do not treat search snippets or community answers as authoritative API evidence.
3. Record the source URL, package/version context, exact symbol coverage, and any compatibility or deprecation caveats. Separate verified facts from inference.
4. Map the findings to the current implementation: `agent/package_registry.py` (registered packages and their docs index), `agent/documentation.py` (index lookup and excerpt extraction), the evidence/status models, citation validation, and `docs/quality-evaluation.md`. A package fits the registry when its official docs publish a machine-readable symbol index (Sphinx `objects.inv` or `llms.txt`) and its pages yield an excerpt for real symbols; verify both against live docs.
5. Keep the registry unchanged unless the user asks to add or remove a package. Do not add package installation, arbitrary code execution, or open-ended discovery that would send unregistered (possibly private) package names to external services, such as PyPI lookups.
6. Present a concise recommendation, implementation implications, and unresolved questions. If implementation is requested, proceed under that scope and update relevant tests and evaluation cases.
