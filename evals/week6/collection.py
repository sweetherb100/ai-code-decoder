"""Collect asynchronous scores without re-running generation or judging locally."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from evals.week6.managed import CATEGORIES, verify_setup


def collect_record(client: Any, record: dict[str, Any], names: list[str]) -> dict[str, Any]:
    """Require one valid categorical EVAL score per expected name on the same root."""
    result = deepcopy(record)
    result.update(scores={}, missing_scores=[], invalid_scores=[])
    if record["outcome"] != "success":
        result["evaluation_status"] = "not_applicable"
        return result
    grouped: dict[str, dict[str, Any]] = {name: {} for name in names}
    cursor = None
    seen = set()
    while True:
        page = client.api.scores.get_many(
            observation_id=record["evaluation_observation_id"],
            trace_id=record["evaluation_trace_id"],
            fields="details,subject",
            limit=100,
            cursor=cursor,
        )
        for score in page.data:
            subject = score.subject
            if (
                score.name in grouped
                and subject
                and subject.kind == "observation"
                and subject.id == record["evaluation_observation_id"]
                and subject.trace_id == record["evaluation_trace_id"]
            ):
                grouped[score.name][score.id] = score
        cursor = page.meta.cursor
        if not cursor:
            break
        if cursor in seen:
            raise RuntimeError("score pagination cursor repeated")
        seen.add(cursor)
    for name, scores in grouped.items():
        if not scores:
            result["missing_scores"].append(name)
            continue
        score = next(iter(scores.values()))
        if (
            len(scores) != 1
            or score.source != "EVAL"
            or score.data_type != "CATEGORICAL"
            or score.value not in CATEGORIES
        ):
            result["invalid_scores"].append(name)
            continue
        result["scores"][name] = {"id": score.id, "value": score.value, "reason": score.comment}
    result["evaluation_status"] = (
        "invalid"
        if result["invalid_scores"]
        else "pending"
        if result["missing_scores"]
        else "complete"
    )
    return result


def collect_once(client: Any, artifact: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    """Check definition stability on both sides of collection; pending stays pending."""
    if artifact["setup"] != lock:
        raise ValueError("setup differs from generated experiment")
    verify_setup(client, lock)
    result = deepcopy(artifact)
    names = [e["name"] for e in lock["evaluators"]]
    result["records"] = [collect_record(client, r, names) for r in artifact["records"]]
    verify_setup(client, lock)
    states = {r["evaluation_status"] for r in result["records"]}
    all_generated = len(result["records"]) == artifact["expected_cases"]
    result["status"] = (
        "invalid"
        if "invalid" in states
        else "pending"
        if "pending" in states or not all_generated or artifact.get("generation_error")
        else "complete"
    )
    return result
