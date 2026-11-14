"""Sequential case execution preserving failures and production guardrails."""

import time
from contextlib import nullcontext
from typing import Any
from unittest.mock import patch

from agent.decoder import decode_code, outcome_for
from agent.evaluation import build_evaluation_input
from agent.models import DocumentationEvidence
from agent.quality import example_syntax_error, is_single_question_format
from evals.week6.dataset import digest
from evals.week6.models import EvalCase


def validate_run(
    cases: list[EvalCase], models: list[str], *, max_requests: int, generation: bool = True
) -> int:
    if len(models) != 2 or len(set(models)) != 2 or not all(models):
        raise ValueError("exactly two different judge models are required")
    if not cases or len({c.case_id for c in cases}) != len(cases):
        raise ValueError("cases must be non-empty with unique IDs")
    # Reserve two generation turns + three metrics for each of two judges.
    # Invalid input is rejected before any call, but reserve conservatively.
    upper_bound = len(cases) * (8 if generation else 6)
    if max_requests < upper_bound:
        raise ValueError(f"request budget requires {upper_bound}, got {max_requests}")
    return upper_bound


def _unavailable(module: str, symbol: str) -> DocumentationEvidence:
    return DocumentationEvidence(
        source_id=f"unavailable:{module}.{symbol}",
        status="unavailable",
        module=module,
        symbol=symbol,
        title="",
        excerpt="",
        url="",
        error_type="TimeoutError",
    )


def run_case(case: EvalCase) -> dict[str, Any]:
    start = time.monotonic()
    record: dict[str, Any] = {
        "case": case.model_dump(),
        "outcome": "runtime_error",
        "outcome_matched": False,
        "evidence": None,
        "generation_usage": None,
        "run_metadata": {},
        "decode_trace_id": None,
        "decode_observation_id": None,
        "rules": {},
        "scores": {},
        "evaluation": None,
        "answer": None,
        "error_type": None,
    }
    try:
        # Test-only failure simulation is scoped to this sequential CLI invocation.
        # Never installed by the application; always restored even on failure.
        manager = (
            patch("agent.pipeline.lookup_documentation", _unavailable)
            if case.documentation_mode == "unavailable"
            else nullcontext()
        )
        with manager:
            execution = decode_code(case.code, case.level, case.context, evaluation_enabled=False)
        docs = [d.model_dump() for d in execution.documentation]
        record["evaluation"] = build_evaluation_input(
            case.code,
            case.level,
            case.context,
            execution,
            expected_facts=case.facts,
            forbidden_claims=case.forbidden_claims,
        ).model_dump(mode="json")
        record["answer"] = execution.result.model_dump()
        record.update(
            outcome="success",
            evidence={
                "answer": execution.result.model_dump(),
                "analysis": execution.analysis.model_dump(),
                "learning_plan": execution.learning_plan.model_dump(),
                "documentation": docs,
                "documentation_hash": digest(docs),
            },
            generation_usage=execution.usage,
            run_metadata=execution.run_metadata,
            decode_trace_id=execution.trace_id,
            decode_observation_id=execution.root_observation_id,
            rules={
                "tool_contract_passed": True,
                "citation_integrity_passed": True,
                "check_format_passed": is_single_question_format(execution.result.check),
                "example_syntax_passed": example_syntax_error(execution.result.example) is None,
            },
        )
    except Exception as exc:
        record["outcome"] = outcome_for(exc)
        record["error_type"] = type(exc).__name__
        rule_by_outcome = {
            "tool_contract_failed": "tool_contract_passed",
            "citation_integrity_failed": "citation_integrity_passed",
        }
        if record["outcome"] in rule_by_outcome:
            record["rules"][rule_by_outcome[record["outcome"]]] = False
    record["generation_latency_seconds"] = time.monotonic() - start
    record["outcome_matched"] = record["outcome"] == case.expected_outcome
    return record
