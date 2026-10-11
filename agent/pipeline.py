"""Deterministic analysis pipeline used by the decode function tool."""

from __future__ import annotations

from typing import Literal

from agent.analyzer import analyze_code
from agent.documentation import lookup_documentation
from agent.models import DecodePipelineEvidence
from agent.planner import build_learning_plan


AudienceLevel = Literal["Beginner", "Developer"]


def run_decode_pipeline(
    code: str,
    surrounding_context: str,
    level: AudienceLevel,
) -> DecodePipelineEvidence:
    """Run static analysis, planning, and selected documentation lookups in order."""
    analysis = analyze_code(code, surrounding_context)
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
