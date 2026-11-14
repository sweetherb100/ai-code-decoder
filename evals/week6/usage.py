"""Read Langfuse's separate judge execution traces; no inference requests."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def collect_usage(client: Any, artifact: dict[str, Any]) -> dict[str, Any]:
    """Join judge observations to exact target roots and the run's evaluation rule.

    Costs are Langfuse estimates, not a provider invoice. Missing values remain
    unknown. An execution may be a retry; score count is not request count.
    """
    targets = {
        (r["evaluation_trace_id"], r["evaluation_observation_id"])
        for r in artifact["records"]
        if r["outcome"] == "success"
    }
    cursor = None
    seen_cursors: set[str] = set()
    executions = {}
    while True:
        page = client.api.observations.get_many(
            environment="langfuse-llm-as-a-judge",
            type="GENERATION",
            fields="basic,model,usage,metadata",
            expand_metadata="*",
            limit=100,
            from_start_time=datetime.fromisoformat(artifact["started_at"]),
            cursor=cursor,
        )
        for observation in page.data:
            metadata = observation.metadata or {}
            if not isinstance(metadata, dict):
                continue
            target = (metadata.get("target_trace_id"), metadata.get("target_observation_id"))
            if (
                target not in targets
                or metadata.get("evaluation_rule_id") != artifact["setup"]["rule_id"]
            ):
                continue
            executions[observation.id] = {
                "id": observation.id,
                "trace_id": observation.trace_id,
                "target_trace_id": target[0],
                "target_observation_id": target[1],
                "model": observation.model or "unknown",
                "usage": observation.usage_details or {},
                "cost_usd": observation.total_cost,
                "evaluator_id": metadata.get("evaluator_id"),
            }
        cursor = page.meta.cursor
        if not cursor:
            break
        if cursor in seen_cursors:
            raise RuntimeError("usage pagination cursor repeated")
        seen_cursors.add(cursor)
    models: dict[str, Any] = {}
    for execution in executions.values():
        group = models.setdefault(
            execution["model"],
            dict(
                executions=0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                known_cost_usd=0.0,
                missing_cost_executions=0,
                missing_usage_executions=0,
            ),
        )
        group["executions"] += 1
        if any(execution["usage"].get(name) is None for name in ("input", "output", "total")):
            group["missing_usage_executions"] += 1
        for name in ("input", "output", "total"):
            group[name + "_tokens"] += execution["usage"].get(name) or 0
        if execution["cost_usd"] is None:
            group["missing_cost_executions"] += 1
        else:
            group["known_cost_usd"] += execution["cost_usd"]
    missing = sum(m["missing_cost_executions"] for m in models.values())
    known = sum(m["known_cost_usd"] for m in models.values())
    evaluator_ids = {e["id"] for e in artifact["setup"].get("evaluators", [])}
    expected = {(t, o, e) for t, o in targets for e in evaluator_ids}
    observed = {
        (e["target_trace_id"], e["target_observation_id"], e["evaluator_id"])
        for e in executions.values()
    }
    missing_targets = len(expected - observed) if evaluator_ids else None
    return dict(
        missing_evaluator_targets=missing_targets,
        token_basis="Observed token subtotals; missing usage is counted separately",
        executions=len(executions),
        expected_base_executions=(len(evaluator_ids) or 6) * len(targets),
        models=models,
        known_cost_usd=known,
        missing_cost_executions=missing,
        total_cost_usd=known if executions and not missing and missing_targets == 0 else None,
        cost_basis="Langfuse calculated estimate, not provider invoice",
        observations=list(executions.values()),
    )
