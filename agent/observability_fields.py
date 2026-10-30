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
    "citation_integrity_failed",
    "agent_behavior_failed",
    "runtime_error",
]
OUTCOMES: frozenset[str] = frozenset(Outcome.__args__)  # type: ignore[attr-defined]

# Root metadata registry. Keys are camelCase because Langfuse metadata keys must be alphanumeric. Prompt keys are added with prompt management.
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
    "temperature": float,
    "reasoningEffort": str,
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

# Score name -> Langfuse data type. Defined in plan section 5.
# Guardrail results: the check blocks the response on failure; the score only
# records the outcome.
GUARDRAIL_SCORE_TYPES: dict[str, str] = {
    "tool_contract_passed": "BOOLEAN",
    "citation_integrity_passed": "BOOLEAN",
    "citation_issue": "CATEGORICAL",
    "check_format_passed": "BOOLEAN",
}
# Reference-free monitoring signals on live traffic. They never block a response
# and are not a substitute for dataset-based offline evaluation.
MONITORING_SCORE_TYPES: dict[str, str] = {
    "exact_resolution_ratio": "NUMERIC",
    "citation_coverage": "NUMERIC",
    "cited_source_count": "NUMERIC",
    "user_feedback": "BOOLEAN",
}
SCORE_TYPES: dict[str, str] = {**GUARDRAIL_SCORE_TYPES, **MONITORING_SCORE_TYPES}
SCORE_NAMES: frozenset[str] = frozenset(SCORE_TYPES)

# When grounding fails for several reasons, the categorical score keeps the
# first one in this order; all codes stay in the evaluator output.
CITATION_ISSUE_PRIORITY: tuple[str, ...] = (
    "missing_field",
    "unverified_source",
    "source_info_mismatch",
    "duplicate_source",
    "missing_source",
    "unexpected_source",
    "invalid_check_format",
    "unverified_concept_source",
    "unknown_concept_target",
    "duplicate_concept",
    "invalid_quiz",
)

# Documentation statuses whose module/symbol are public Python names. Other
# statuses may carry private package names taken from the submitted code.
PUBLIC_DOC_STATUSES: frozenset[str] = frozenset({"exact_match", "page_only", "unavailable"})

# Exported OTel attributes. Anything else is deleted at export time by the mask
# hook. Langfuse keys are listed exactly (no `langfuse.` wildcard) so a stray
# metadata key or a new SDK attribute cannot slip through unreviewed.
ALLOWED_ATTRIBUTE_KEYS: frozenset[str] = frozenset(
    {
        # OpenInference (model, token, and span-kind facts; no content)
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
        # Langfuse first-class attributes
        "langfuse.environment",
        "langfuse.release",
        "langfuse.internal.is_app_root",
        "langfuse.trace.name",
        "langfuse.trace.tags",
        "langfuse.observation.type",
        "langfuse.observation.level",
        "langfuse.observation.status_message",
        "langfuse.observation.prompt.name",
        "langfuse.observation.prompt.version",
        # Manual observation payloads. Their content is limited by
        # OBSERVATION_PAYLOAD_KEYS before they are set.
        "langfuse.observation.input",
        "langfuse.observation.output",
    }
)
ALLOWED_ATTRIBUTE_PREFIXES: tuple[str, ...] = ("llm.token_count.",)
METADATA_ATTRIBUTE_PREFIX = "langfuse.observation.metadata."
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

# Allowed input/output keys per manual observation (plan 4.4). Keys outside this
# schema are dropped before the payload reaches the span, so raw code passed by
# mistake never leaves the process. The root accepts raw content keys only when
# content capture is on.
OBSERVATION_PAYLOAD_KEYS: dict[str, dict[str, frozenset[str]]] = {
    ROOT_OBSERVATION_NAME: {
        "input": frozenset({"codeChars", "contextChars", "level"}),
        "output": frozenset(
            {"whatCount", "sourceCount", "hasExample", "conceptCount", "quizOptionCount"}
        ),
    },
    "validate_input.analyze_code": {
        "input": frozenset({"codeChars", "contextChars"}),
        "output": frozenset({"importCount", "targetCount", "resolvedCount", "syntaxTopics"}),
    },
    "prompt.resolve": {
        "input": frozenset({"name", "label"}),
        "output": frozenset(
            {
                "source",
                "version",
                "modelSource",
                "temperature",
                "reasoningEffort",
                "fallbackReason",
            }
        ),
    },
    "build_learning_plan": {
        "input": frozenset({"targetCount", "level"}),
        "output": frozenset({"primaryTargetIds", "excludedCount", "syntaxTopics"}),
    },
    "lookup_documentation": {
        "input": frozenset({"module", "symbol"}),
        "output": frozenset({"status", "sourceId", "url", "excerptChars", "errorType"}),
    },
    "validate_output.pipeline_evidence": {
        "input": frozenset({"toolCallCount"}),
        "output": frozenset({"passed", "expectedDocumentCount", "returnedDocumentCount"}),
    },
    "validate_output.citation_integrity": {
        "input": frozenset({"exactEvidenceCount", "citedCount"}),
        "output": frozenset({"passed", "issueCodes"}),
    },
}
ROOT_CONTENT_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "input": frozenset({"code", "context", "level"}),
    "output": frozenset({"what", "why", "source", "example", "check", "concepts", "quiz"}),
}


def is_allowed_attribute(key: str, *, capture_content: bool) -> bool:
    """Return whether an OTel attribute may be exported."""
    if key in ALLOWED_ATTRIBUTE_KEYS or key.startswith(ALLOWED_ATTRIBUTE_PREFIXES):
        return True
    if key.startswith(METADATA_ATTRIBUTE_PREFIX):
        return key[len(METADATA_ATTRIBUTE_PREFIX):] in ROOT_METADATA_KEYS
    if not capture_content:
        return False
    return key in CONTENT_ATTRIBUTE_KEYS or key.startswith(CONTENT_ATTRIBUTE_PREFIXES)


def allowed_payload_keys(name: str, field: str, *, capture_content: bool) -> frozenset[str]:
    """Return the input/output keys a manual observation may record."""
    keys = OBSERVATION_PAYLOAD_KEYS.get(name, {}).get(field, frozenset())
    if capture_content and name == ROOT_OBSERVATION_NAME:
        keys = keys | ROOT_CONTENT_PAYLOAD_KEYS[field]
    return keys
