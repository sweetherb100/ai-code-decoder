---
name: prompt-change-evaluation
description: Change or evaluate AI Code Decode system prompts, audience instructions, structured outputs, or prompt version/config behavior, including Langfuse prompt rollout.
---

# Prompt Change and Evaluation

Use this skill for prompt or prompt-configuration work in this repository.

1. Read the prompt resolution and schema code in `agent/prompts.py`, `agent/models.py`, and `agent/decoder.py`; check the prompt management section of `README.md`.
2. Preserve the response contract: What / Why / Source / Example / Check, the selected Beginner or Developer level, and exactly one check question, unless the request explicitly changes that contract.
3. If the output shape or function-tool contract changes, review `PROMPT_SCHEMA_VERSION` and the documented remote-prompt fallback behavior. Do not silently reuse an incompatible remote prompt.
4. Update the local prompt and the focused prompt tests for the requested behavior. Review the matching cases in `docs/quality-evaluation.md` and update a scenario when user-visible expectations change.
5. If asked to seed a prompt, use `scripts/seed_prompts.py` as documented. Seed to `staging` for evaluation; changing the Langfuse `production` label is a separate remote release action and requires explicit user authorization.
6. Report which prompt source/version was changed and which checks were actually performed. Do not claim model quality from static inspection alone.
