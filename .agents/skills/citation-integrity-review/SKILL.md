---
name: citation-integrity-review
description: Review or change how AI Code Decode finds, represents, or validates Python documentation evidence and final citations.
---

# Citation Integrity Review

Use this skill when a task concerns documentation lookup, evidence statuses, source IDs, or citations in generated explanations.

1. Trace the evidence flow through `agent/documentation.py`, `agent/package_registry.py`, `agent/models.py`, `agent/quality.py`, and the relevant pipeline code before proposing changes.
2. Treat `exact_match` as the only citeable status. A final citation must match the tool evidence's source ID, title, and URL exactly; `page_only`, `unsupported`, and `unavailable` are not citations.
3. Preserve the existing support boundary: Python docs for built-ins and the standard library, plus registered third-party packages resolved through their own docs index (Sphinx `objects.inv` or `llms.txt`). `exact_match` requires an exact symbol entry in that index (or a single unambiguous re-export) and a non-empty excerpt; a parent page or docs home is at most `page_only`. Never infer an instance's type or invent a documentation match.
4. Consult citation-related cases in `docs/quality-evaluation.md`. For a behavior change, add or adjust focused tests and evaluation scenarios as appropriate.
5. If checking live documentation is needed, use the official source and report retrieval failures separately from unsupported symbols.
6. Summarize evidence paths and edge cases reviewed. Distinguish observed behavior from proposed behavior.
