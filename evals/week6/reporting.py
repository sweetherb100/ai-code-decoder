"""Completion and regression reporting; distributions remain in Langfuse Analytics."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

RANK = {"incorrect": 0, "deficient": 1, "adequate": 2, "excellent": 3}


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    """Write a new result without overwriting previous evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(artifact, output, ensure_ascii=False, indent=2)
        output.write("\n")


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep missing judgments and shared control mistakes in the denominator."""
    controls = []
    metric_checks = []
    for record in records:
        for metric, allowed in record.get("expected_categories", {}).items():
            for role in ("primary", "secondary"):
                values = [
                    s["value"]
                    for name, s in record.get("scores", {}).items()
                    if name.endswith(f".{role}.{metric}")
                ]
                value = values[0] if len(values) == 1 else None
                metric_checks.append(
                    {
                        "case_id": record["case"]["case_id"],
                        "role": role,
                        "metric": metric,
                        "value": value,
                        "passed": value in allowed if value is not None else None,
                    }
                )
        if "expected_control_error" not in record:
            continue
        checks = {}
        for role in ("primary", "secondary"):
            values = [
                s["value"]
                for name, s in record.get("scores", {}).items()
                if name.endswith(f".{role}.semantic_correctness")
            ]
            value = values[0] if len(values) == 1 else None
            checks[role] = (
                (
                    value in ("incorrect", "deficient")
                    if record["expected_control_error"]
                    else value in ("adequate", "excellent")
                )
                if value in RANK
                else None
            )
        controls.append(checks)
    return {
        "total": len(records),
        "outcomes": dict(Counter(r["outcome"] for r in records)),
        "evaluation_statuses": dict(
            Counter(r.get("evaluation_status", "pending") for r in records)
        ),
        "control_checks": controls,
        "metric_control_checks": metric_checks,
        "shared_control_failures": sum(all(v is False for v in c.values()) for c in controls),
    }


def compare_runs(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare fixed cases and protocols; never rank unscorable categories as zero."""
    if baseline["protocol"] != candidate["protocol"]:
        raise ValueError("evaluation protocol differs")
    if any(r.get("status") != "complete" for r in (baseline, candidate)):
        raise ValueError("both runs must be complete before comparison")
    left = {r["case"]["case_id"]: r for r in baseline["records"]}
    right = {r["case"]["case_id"]: r for r in candidate["records"]}
    if (
        not left
        or left.keys() != right.keys()
        or len(left) != len(baseline["records"])
        or len(right) != len(candidate["records"])
    ):
        raise ValueError("case sets differ, are duplicated or empty")
    rows = []
    for case_id, before in left.items():
        after = right[case_id]
        if before["case"] != after["case"]:
            raise ValueError("case contents differ")
        transitions = {}
        regressions = []
        for name in before.get("scores", {}).keys() | after.get("scores", {}).keys():
            a = before.get("scores", {}).get(name, {}).get("value")
            b = after.get("scores", {}).get(name, {}).get("value")
            transitions[name] = {"before": a, "after": b}
            if a in RANK and b in RANK and RANK[b] < RANK[a]:
                regressions.append(name)
        before_config = before.get("run_metadata", {})
        after_config = after.get("run_metadata", {})
        config_changes = {
            key: {"before": before_config.get(key), "after": after_config.get(key)}
            for key in ("model", "temperature", "reasoningEffort")
            if before_config.get(key) != after_config.get(key)
        }
        caveats = []
        if config_changes:
            caveats.append("generation_settings_changed")
        if not before_config.get("model") or not after_config.get("model"):
            caveats.append("generation_settings_unavailable")
        rows.append(
            {
                "case_id": case_id,
                "before_outcome": before["outcome"],
                "after_outcome": after["outcome"],
                "transitions": transitions,
                "generation_config_changes": config_changes,
                "comparison_caveats": caveats,
                "regressions": sorted(regressions),
                "documentation_changed": (before.get("evaluation") or {}).get("documentation_hash")
                != (after.get("evaluation") or {}).get("documentation_hash"),
            }
        )
    return {
        "baseline": summarize(baseline["records"]),
        "candidate": summarize(candidate["records"]),
        "cases": rows,
    }
