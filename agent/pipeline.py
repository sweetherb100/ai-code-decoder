"""Deterministic analysis pipeline used by the decode function tool."""

from __future__ import annotations

from typing import Literal

from agent.documentation import lookup_documentation
from agent.models import CodeAnalysis, DecodePipelineEvidence, DocumentationEvidence
from agent.observability import observation
from agent.observability_fields import PUBLIC_DOC_STATUSES
from agent.planner import build_learning_plan


AudienceLevel = Literal["Beginner", "Developer"]


def run_decode_pipeline(
    analysis: CodeAnalysis,
    level: AudienceLevel,
) -> DecodePipelineEvidence:
    """Build a learning plan and look up selected docs for pre-analyzed code."""
    with observation(
        "build_learning_plan",
        input={"targetCount": len(analysis.learning_targets), "level": level},
    ) as plan_span:
        learning_plan = build_learning_plan(
            analysis.learning_targets,
            analysis.syntax,
            level,
        )
        plan_span.update(
            output={
                "primaryTargetIds": [item.target_id for item in learning_plan.primary_targets],
                "excludedCount": len(learning_plan.excluded_targets),
                "syntaxTopics": learning_plan.syntax_topics,
            }
        )
    targets_by_id = {
        target.target_id: target for target in analysis.learning_targets
    }
    documentation = [
        _traced_lookup(
            targets_by_id[plan_item.target_id].module,
            targets_by_id[plan_item.target_id].symbol,
        )
        for plan_item in learning_plan.primary_targets
    ]
    return DecodePipelineEvidence(
        analysis=analysis,
        learning_plan=learning_plan,
        documentation=documentation,
    )


def _traced_lookup(module: str, symbol: str) -> DocumentationEvidence:
    """Look up documentation, recording names only for public Python targets."""
    with observation("lookup_documentation", as_type="retriever") as span:
        evidence = lookup_documentation(module, symbol)
        is_public = evidence.status in PUBLIC_DOC_STATUSES
        output = {
            "status": evidence.status,
            "sourceId": evidence.source_id,
            "url": evidence.url,
            "excerptChars": len(evidence.excerpt),
        }
        if evidence.error_type:
            output["errorType"] = evidence.error_type
        span.update(
            # Unsupported targets can carry private package names from user code.
            input={"module": module, "symbol": symbol} if is_public else {},
            output=output,
        )
        if evidence.status == "unavailable":
            span.update(level="WARNING", status_message=evidence.error_type or "unavailable")
        return evidence
