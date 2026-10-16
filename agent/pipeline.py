"""Deterministic analysis pipeline used by the decode function tool."""

from __future__ import annotations

from typing import Literal

from agent.documentation import lookup_documentation
from agent.models import CodeAnalysis, DecodePipelineEvidence
from agent.planner import build_learning_plan


AudienceLevel = Literal["Beginner", "Developer"]


def run_decode_pipeline(
    analysis: CodeAnalysis,
    level: AudienceLevel,
) -> DecodePipelineEvidence:
    """Build a learning plan and look up selected docs for pre-analyzed code."""
    learning_plan = build_learning_plan(
        analysis.learning_targets,
        analysis.syntax,
        level,
    )
    targets_by_id = {
        target.target_id: target for target in analysis.learning_targets
    }
    documentation = [
        lookup_documentation(
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
