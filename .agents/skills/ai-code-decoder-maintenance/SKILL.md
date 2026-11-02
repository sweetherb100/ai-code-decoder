---
name: ai-code-decoder-maintenance
description: Make or review changes to this AI Code Decode Agent project, especially its Python AST analysis, learning pipeline, Python documentation citations, Agents SDK orchestration, prompts, Streamlit UI, or Langfuse tracing. Use when a task needs project-specific context or quality checks.
---

# AI Code Decoder Maintenance

Use this skill for changes in this repository. It gives project context and a repeatable review workflow; it does not replace the user's task request or repository instructions.

## Before changing code

1. Read applicable `AGENTS.md` files and the relevant sections of `README.md`.
2. Inspect the affected implementation and nearby tests before editing. Follow the existing architecture and naming, and the rules in `docs/code-convention.md`.
3. Use `docs/quality-evaluation.md` for representative end-to-end behaviors and `docs/pr-description.md` for design history when relevant.
4. Identify whether the change affects the public `DecodeResult`, function-tool contract, prompt schema, documentation evidence, or tracing fields. If the output/tool contract changes, check `PROMPT_SCHEMA_VERSION` and the prompt seeding workflow in `README.md`.

## Project invariants

- User-submitted Python is data. Parse it with the AST; never execute it as part of analysis or a test fixture.
- Keep the decode flow deterministic: analyze code, build a learning plan, look up official documentation only for selected targets, then generate and validate the explanation.
- Cite only exact documentation matches returned by the documentation lookup. Never invent source IDs, titles, URLs, or excerpts.
- Preserve the supported documentation boundary: Python docs for built-ins and the standard library, and each registered package's own official docs for packages in `agent/package_registry.py`. Report unregistered packages as unsupported without any documentation request, so their (possibly private) names never reach docs sites, package indexes, or telemetry. Rank third-party targets by the same criteria as built-ins; do not deprioritize them. Adding a package to the registry follows the `external-package-docs-research` skill.
- Keep submitted code and surrounding context out of persistent storage and telemetry by default. Review trace inputs, outputs, metadata, and errors for accidental content or private identifiers when changing observability.
- Preserve the existing single top-level `decode_code_pipeline` function-tool contract unless the requested behavior requires changing it. Do not add autonomous tool selection or sub-agents without a concrete user requirement.
- Keep Beginner and Developer audience behavior, one-question check format, and What / Why / Source / Example / Check response structure intact unless the request changes them.

## Implement and verify

1. Make the smallest change that satisfies the request.
2. Update focused tests for changed behavior when tests are requested or needed to establish correctness. Avoid live API calls unless the task requires them.
3. For changes to the decode flow, citation rules, or prompt behavior, consult the matching scenarios in `docs/quality-evaluation.md` and add or revise a scenario when the expected user-visible behavior changes.
4. Run only the relevant checks. The project test command is `python -m pytest tests`; lint and format checks are `ruff check <changed files>` and `ruff format --check <changed files>` (install with `pip install ruff==0.17.2`). Setup and dependency guidance are in `README.md`.
5. Review the diff for scope, privacy, citation integrity, and consistency between implementation, tests, docs, and prompt schema.
6. Report the files changed, checks actually run, and any unverified behavior. Never claim a test or live model run that did not happen.
