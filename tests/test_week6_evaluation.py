"""Dataset invariants retained across evaluation backends."""

import json

import pytest


def test_dataset_has_paired_levels_without_split_leakage():
    from evals.week6.dataset import load_cases

    cases = load_cases()
    assert len(cases) == 24
    groups = {}
    for case in cases:
        groups.setdefault(case.group_id, []).append(case)
    assert len(groups) == 12
    assert sum(c.split == "holdout" for c in cases) == 8
    for group in groups.values():
        assert {c.level for c in group} == {"Beginner", "Developer"}
        assert len({c.split for c in group}) == 1


def test_dataset_rejects_identical_input_across_splits(tmp_path):
    from evals.week6.dataset import load_cases

    cases = load_cases()
    path = tmp_path / "cases.jsonl"
    original = cases[0].model_dump()
    copy = {**original, "case_id": "other", "group_id": "other", "split": "holdout"}
    path.write_text(json.dumps(original) + "\n" + json.dumps(copy))
    with pytest.raises(ValueError, match="splits"):
        load_cases(path)


def test_control_expectations_cover_each_metric_without_leaking_to_judge():
    import json

    from evals.week6.controls import load_controls, run_control
    from evals.week6.reporting import summarize

    controls = load_controls()
    assert {"evidence_faithfulness", "audience_fit"} <= {
        metric for c in controls for metric in c.get("expected_categories", {})
    }
    for c in controls:
        r = run_control(c)
        if c.get("expected_categories"):
            assert r["expected_categories"] == c["expected_categories"]
            assert "expected_categories" not in json.dumps(r["evaluation"])
            r["scores"] = {
                f"v.{role}.{metric}": {"value": allowed[0]}
                for metric, allowed in c["expected_categories"].items()
                for role in ("primary", "secondary")
            }
            assert all(row["passed"] for row in summarize([r])["metric_control_checks"])
