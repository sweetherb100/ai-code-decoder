---
name: langfuse-trace-review
description: Change or audit AI Code Decode Langfuse tracing, observations, scores, prompt metadata, or telemetry privacy behavior.
---

# Langfuse Trace Review

Use this skill when modifying or investigating tracing, score fields, trace exports, or telemetry privacy.

1. Read `README.md`'s Langfuse data policy and `docs/quality-evaluation.md`'s trace expectations. Inspect the relevant code in `agent/observability.py`, `agent/observability_fields.py`, `agent/decoder.py`, and associated tests.
2. Treat telemetry as a data boundary: with default settings, submitted code, surrounding context, model response text, and names of unregistered third-party packages must not be exported. Module and symbol names of packages registered in `agent/package_registry.py` are public and may appear in retriever inputs. Preserve the documented opt-in conditions for content capture.
3. When changing a trace field or score, update the central field registry and relevant trace tests/evaluation expectations together. Check both success and failure paths, including unsupported and unavailable documentation lookups.
4. Prefer synthetic fixtures and in-memory export capture. Do not send real user code or enable content capture to inspect traces unless the user explicitly requests that and the destination is appropriate.
5. Report the exact fields and paths inspected, the privacy behavior established by evidence, and any cases not exercised. Do not claim privacy guarantees beyond the inspected/exported paths.
