"""Registry of telemetry names exported to Langfuse.

Every root metadata key, outcome, score name, and exported OTel attribute must be
listed here. Tests fail when code uses a name that is not registered, so a typo
cannot silently break dashboards and a new instrumentation attribute cannot leak
content without review.
"""

from __future__ import annotations

from typing import Literal


TRACE_NAME = "code-decode"
ROOT_OBSERVATION_NAME = "decode_code"
APP_TAG = "app:code-decoder"

Outcome = Literal[
    "success",
    "input_rejected",
    "tool_contract_failed",
    "grounding_failed",
    "agent_behavior_failed",
    "runtime_error",
]
OUTCOMES: frozenset[str] = frozenset(Outcome.__args__)  # type: ignore[attr-defined]

# Root metadata registry. Keys are camelCase because Langfuse metadata keys must
# be alphanumeric. Prompt keys are added with prompt management (phase 2).
ROOT_METADATA_KEYS: dict[str, type] = {
    "outcome": str,
    "model": str,
    "modelSource": str,
    "codeChars": int,
    "contextChars": int,
    "hasContext": bool,
    "maxTurns": int,
    "targetCount": int,
    "unresolvedTargetCount": int,
    "primaryTargetCount": int,
    "docsExactMatchCount": int,
    "docsPageOnlyCount": int,
    "docsUnsupportedCount": int,
    "docsUnavailableCount": int,
    "llmCallCount": int,
    "contentCaptured": bool,
    "promptSource": str,
    "promptVersion": str,
    "promptFallbackReason": str,
}

PROMPT_SOURCES: frozenset[str] = frozenset({"langfuse", "fallback"})
PROMPT_FALLBACK_REASONS: frozenset[str] = frozenset(
    {
        "disabled",
        "fetch_failed",
        "type_mismatch",
        "schema_mismatch",
        "invalid_config",
        "compile_failed",
        "unexpected",
    }
)

SCORE_NAMES: frozenset[str] = frozenset({"tool_contract_passed", "grounding_passed"})

# Documentation statuses whose module/symbol are public Python names. Other
# statuses may carry private package names taken from the submitted code.
PUBLIC_DOC_STATUSES: frozenset[str] = frozenset({"exact_match", "page_only", "unavailable"})

# Exported OTel attributes, by exact key or prefix. Anything else is deleted at
# export time by the mask hook. Content keys (input/output values, tool schemas)
# are intentionally absent; they are only exported when content capture is on.
ALLOWED_ATTRIBUTE_KEYS: frozenset[str] = frozenset(
    {
        "agent.name",
        "graph.node.id",
        "graph.node.parent_id",
        "llm.finish_reason",
        "llm.model_name",
        "llm.provider",
        "llm.system",
        "openinference.span.kind",
        "session.id",
        "tool.name",
    }
)
ALLOWED_ATTRIBUTE_PREFIXES: tuple[str, ...] = (
    "langfuse.",
    "llm.token_count.",
)
CONTENT_ATTRIBUTE_KEYS: frozenset[str] = frozenset(
    {
        "input.value",
        "input.mime_type",
        "output.value",
        "output.mime_type",
        "llm.invocation_parameters",
        "tool.description",
        "tool.parameters",
    }
)
CONTENT_ATTRIBUTE_PREFIXES: tuple[str, ...] = (
    "llm.input_messages.",
    "llm.output_messages.",
    "llm.tools.",
)


def is_allowed_attribute(key: str, *, capture_content: bool) -> bool:
    """Return whether an OTel attribute may be exported."""
    if key in ALLOWED_ATTRIBUTE_KEYS or key.startswith(ALLOWED_ATTRIBUTE_PREFIXES):
        return True
    if not capture_content:
        return False
    return key in CONTENT_ATTRIBUTE_KEYS or key.startswith(CONTENT_ATTRIBUTE_PREFIXES)
