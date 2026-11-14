"""Fixed synthetic contrast pairs, with expected labels kept out of judge input."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.analyzer import analyze_code
from agent.decoder import DecodeExecution
from agent.evaluation import build_evaluation_input
from agent.models import DecodeResult, DocumentationEvidence
from agent.planner import build_learning_plan
from evals.week6.models import EvalCase


def load_controls() -> list[dict[str, Any]]:
    """Load designed controls; these are not human-validated ground truth."""
    return json.loads(Path(__file__).with_name("controls.json").read_text())


def run_control(control: dict[str, Any]) -> dict[str, Any]:
    """Prepare a fixed answer for server-side evaluation without model calls."""
    case = EvalCase.model_validate(control["case"])
    analysis = analyze_code(case.code, case.context)
    execution = DecodeExecution(
        result=DecodeResult.model_validate(control["evidence"]["answer"]),
        analysis=analysis,
        learning_plan=build_learning_plan(analysis.learning_targets, analysis.syntax, case.level),
        documentation=[
            DocumentationEvidence.model_validate(d) for d in control["evidence"]["documentation"]
        ],
        tool_call_audit=[],
        run_metadata={"source": "fixed_control"},
    )
    return {
        "case": case.model_dump(),
        "outcome": "success",
        "outcome_matched": True,
        "evaluation": build_evaluation_input(
            case.code,
            case.level,
            case.context,
            execution,
            expected_facts=case.facts,
            forbidden_claims=case.forbidden_claims,
        ).model_dump(mode="json"),
        "answer": execution.result.model_dump(),
        "scores": {},
        "expected_control_error": control["expected_critical_error"],
        "expected_categories": control.get("expected_categories", {}),
        "generation_usage": {"requests": 0, "total_tokens": 0},
        "generation_latency_seconds": 0,
        "rules": {},
    }
