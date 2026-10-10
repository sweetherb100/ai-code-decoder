"""Deterministic tool workflow used before generating a decode response."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from agent.analyzer import analyze_code
from agent.documentation import lookup_documentation
from agent.models import CodeAnalysis, LearningPlan
from agent.planner import build_learning_plan


AudienceLevel = Literal["Beginner", "Developer"]


@dataclass
class ToolWorkflow:
    analysis: CodeAnalysis
    learning_plan: LearningPlan
    documentation: list[dict[str, str | bool]]


def run_tool_workflow(
    code: str,
    context: str,
    level: AudienceLevel,
    analysis: Optional[CodeAnalysis] = None,
) -> ToolWorkflow:
    """Run analysis, planning, and selected documentation lookups in order."""
    code_analysis = analysis or analyze_code(code, context)
    learning_plan = build_learning_plan(
        code_analysis.learning_targets,
        code_analysis.syntax,
        level,
    )
    targets_by_id = {
        target.target_id: target for target in code_analysis.learning_targets
    }
    documentation: list[dict[str, str | bool]] = []
    for plan_item in learning_plan.primary_targets:
        target = targets_by_id[plan_item.target_id]
        documentation.append(
            {
                "target_id": target.target_id,
                "target_name": target.name,
                "expression": target.expression,
                **lookup_documentation(target.module, target.symbol),
            }
        )

    return ToolWorkflow(
        analysis=code_analysis,
        learning_plan=learning_plan,
        documentation=documentation,
    )
