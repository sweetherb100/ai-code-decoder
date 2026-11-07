"""App evidence privacy and managed evaluation integration contracts."""

from __future__ import annotations

import json


def test_app_evaluation_is_opt_in_and_does_not_unmask_children(
    fake_openai, stub_docs, span_exporter, monkeypatch
):
    from agent import observability
    from agent.decoder import decode_code

    monkeypatch.setenv("LANGFUSE_EVALUATION_ENABLED", "1")
    execution = decode_code("private_value = 123", "Beginner", "private_context = 1")
    observability.flush()
    spans = [
        s
        for s in span_exporter.get_finished_spans()
        if format(s.context.trace_id, "032x") == execution.trace_id
    ]
    root = next(s for s in spans if s.name == "decode_code")
    payload = json.loads(root.attributes["langfuse.observation.input"])
    assert payload["evaluation"]["code"] == "private_value = 123"
    assert payload["evaluation"]["context"] == "private_context = 1"
    assert payload["evaluation"]["level"] == "Beginner"
    assert "documentation" in payload["evaluation"]
    assert json.loads(root.attributes["langfuse.observation.output"])["answer"]["check"]
    assert (
        json.loads(root.attributes["langfuse.observation.metadata.evaluationSchema"])
        == "code-decoder-v2"
    )
    assert len(fake_openai.requests) == 2
    assert all("private_value" not in str(s.attributes) for s in spans if s != root)


def test_explicit_disabled_evaluation_overrides_environment(
    fake_openai, stub_docs, span_exporter, monkeypatch
):
    from agent import observability
    from agent.decoder import decode_code

    monkeypatch.setenv("LANGFUSE_EVALUATION_ENABLED", "1")
    execution = decode_code("private_value = 123", "Beginner", evaluation_enabled=False)
    observability.flush()
    spans = [
        s
        for s in span_exporter.get_finished_spans()
        if format(s.context.trace_id, "032x") == execution.trace_id
    ]
    assert all("private_value" not in str(s.attributes) for s in spans)


def test_managed_definitions_pair_models_and_preserve_unscorable_categories():
    from evals.week6.managed import evaluator_definitions, rule_filters

    definitions = evaluator_definitions(["judge-a", "judge-b"], "openai")
    assert len(definitions) == 6
    assert {d.model_config_.model for d in definitions} == {"judge-a", "judge-b"}
    assert len({d.name for d in definitions}) == 6
    for definition in definitions:
        assert definition.output_definition.categories == [
            "excellent",
            "adequate",
            "deficient",
            "incorrect",
            "insufficient_evidence",
            "not_applicable",
        ]
        assert not definition.output_definition.should_allow_multiple_matches
        assert {v.variable for v in definition.variable_mapping} == {"evidence", "answer"}
        assert all(v.json_path in ("$.evaluation", "$.answer") for v in definition.variable_mapping)
    filters = [f.model_dump() for f in rule_filters("protocol", "study")]
    assert any(f.get("key") == "evaluationProtocol" and f["value"] == "protocol" for f in filters)
    assert any(f["column"] == "environment" and "study" in f["value"] for f in filters)


def test_managed_budget_accounts_for_six_judges():
    import pytest

    from evals.week6.dataset import load_cases
    from evals.week6.experiment import validate_run

    with pytest.raises(ValueError, match="budget"):
        validate_run(load_cases()[:2], ["a", "b"], max_requests=15)
    assert validate_run(load_cases()[:2], ["a", "b"], max_requests=16) == 16
    assert validate_run(load_cases()[:2], ["a", "b"], max_requests=12, generation=False) == 12


def test_managed_experiment_records_item_evidence_without_app_duplicate(
    fake_openai, stub_docs, span_exporter, monkeypatch
):
    from agent import observability
    from evals.week6.dataset import load_cases
    from evals.week6.langfuse_runner import run_experiment

    client = observability.prompt_client()
    monkeypatch.setattr(client, "_get_project_id", lambda: "test-project")
    monkeypatch.setenv("LANGFUSE_EVALUATION_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_EVALUATION_SAMPLE_RATE", "0")
    case = load_cases()[0]
    result, records = run_experiment(
        client,
        [case],
        run_name="managed-test",
        data=[{"input": case.model_dump()}],
        metadata={"evaluationProtocol": "test-protocol"},
    )
    observability.flush()
    task = [s for s in span_exporter.get_finished_spans() if s.name == "experiment-item-task"][-1]
    app = [s for s in span_exporter.get_finished_spans() if s.name == "decode_code"][-1]
    assert app.context.trace_id == task.context.trace_id
    assert "evaluation" not in json.loads(app.attributes["langfuse.observation.input"])
    assert "langfuse.observation.metadata.evaluationSchema" not in app.attributes
    assert (
        json.loads(task.attributes["langfuse.observation.input"])["evaluation"]["code"] == case.code
    )
    assert json.loads(task.attributes["langfuse.observation.output"])["answer"]["check"]
    assert records[0]["evaluation_observation_id"] == format(task.context.span_id, "016x")
    from evals.week6.managed import rule_filters

    environments = next(
        f.value for f in rule_filters("test-protocol", "study") if f.column == "environment"
    )
    assert task.attributes["langfuse.environment"] in environments
    assert result.item_results[0].evaluations == []
    assert len(fake_openai.requests) == 2


def test_score_collection_keeps_missing_and_duplicate_results_visible():
    from types import SimpleNamespace as Obj

    from evals.week6.collection import collect_record

    names = [
        f"v.primary.{m}" for m in ("semantic_correctness", "evidence_faithfulness", "audience_fit")
    ]
    record = {
        "outcome": "success",
        "evaluation_observation_id": "obs",
        "evaluation_trace_id": "trace",
    }
    values = [
        Obj(
            id="s1",
            name=names[0],
            value="adequate",
            data_type="CATEGORICAL",
            source="EVAL",
            comment="reason",
            subject=Obj(kind="observation", id="obs", trace_id="trace"),
        )
    ]

    class Scores:
        def get_many(self, **kwargs):
            return Obj(data=values, meta=Obj(cursor=None))

    client = Obj(api=Obj(scores=Scores()))
    result = collect_record(client, record, names)
    assert result["evaluation_status"] == "pending"
    assert result["missing_scores"] == names[1:]
    values.extend([Obj(**{**vars(values[0]), "id": "s2"})])
    result = collect_record(client, record, names)
    assert result["evaluation_status"] == "invalid"
    assert result["invalid_scores"] == [names[0]]


def test_controls_report_shared_error_without_a_human_label_in_payload():
    from evals.week6.controls import load_controls, run_control
    from evals.week6.reporting import summarize

    bad = load_controls()[1]
    record = run_control(bad)
    assert "expected_critical_error" not in json.dumps(record["evaluation"])
    record["scores"] = {
        f"v.{role}.semantic_correctness": {"value": "excellent"}
        for role in ("primary", "secondary")
    }
    result = summarize([record])
    assert result["shared_control_failures"] == 1


def test_compare_rejects_incomplete_and_flags_regressions():
    from copy import deepcopy

    import pytest

    from evals.week6.reporting import compare_runs

    base = {"protocol": {}, "status": "pending", "records": []}
    with pytest.raises(ValueError, match="complete"):
        compare_runs(base, base)
    base.update(
        status="complete",
        records=[
            {
                "case": {"case_id": "one"},
                "outcome": "success",
                "outcome_matched": True,
                "scores": {"v.primary.semantic_correctness": {"value": "adequate"}},
            }
        ],
    )
    other = deepcopy(base)
    other["records"][0]["scores"]["v.primary.semantic_correctness"]["value"] = "incorrect"
    assert compare_runs(base, other)["cases"][0]["regressions"] == [
        "v.primary.semantic_correctness"
    ]


def test_setup_version_drift_and_mapping_override_block_collection():
    from types import SimpleNamespace as Obj

    import pytest

    from evals.week6.managed import setup_evaluators, verify_setup

    stored = {}

    class Evaluators:
        def create(self, request):
            entry = Obj(
                id=str(len(stored)), version=1, version_id="v1", name=request.name, status="active"
            )
            stored[entry.id] = entry
            return entry

        def get(self, evaluator_id):
            return stored[evaluator_id]

    class Rules:
        def create(self, **kwargs):
            self.rule = Obj(id="rule", **kwargs)
            return self.rule

        def get(self, rule_id):
            return self.rule

    client = Obj(api=Obj(evaluators=Evaluators(), evaluation_rules=Rules()))
    lock = setup_evaluators(
        client, ["a", "b"], "openai", "study", protocol="test", on_progress=lambda _: None
    )
    verify_setup(client, lock)
    stored["0"].status = "paused"
    with pytest.raises(ValueError, match="paused"):
        verify_setup(client, lock)
    stored["0"].status = "active"
    stored["0"].version = 2
    with pytest.raises(ValueError, match="version"):
        verify_setup(client, lock)
    stored["0"].version = 1
    # A UI rule override can silently give the model the wrong input.
    client.api.evaluation_rules.rule.evaluator_assignments = [
        Obj(evaluator_id=e["id"], variable_mapping=[{"variable": "answer", "source": "input"}])
        for e in lock["evaluators"]
    ]
    with pytest.raises(ValueError, match="mapping"):
        verify_setup(client, lock)


def test_invalid_input_is_not_evaluated_and_unavailable_docs_stay_explicit(
    fake_openai, stub_docs, span_exporter
):
    from agent import pipeline
    from evals.week6.dataset import load_cases
    from evals.week6.experiment import run_case

    record = run_case(next(c for c in load_cases() if c.group_id == "invalid"))
    assert record["outcome"] == "input_rejected"
    assert record["evaluation"] is None
    assert not fake_openai.requests
    original = pipeline.lookup_documentation
    record = run_case(next(c for c in load_cases() if c.group_id == "unavailable"))
    assert record["outcome"] == "success"
    assert all(d["status"] == "unavailable" for d in record["evaluation"]["documentation"])
    assert pipeline.lookup_documentation is original


def test_comparison_surfaces_generation_settings_changed_alongside_prompt():
    from copy import deepcopy

    from evals.week6.reporting import compare_runs

    base = {
        "protocol": {},
        "status": "complete",
        "records": [
            {
                "case": {"case_id": "one"},
                "outcome": "success",
                "run_metadata": {"model": "model-a", "temperature": 0.2, "promptVersion": 1},
                "scores": {},
            }
        ],
    }
    candidate = deepcopy(base)
    candidate["records"][0]["run_metadata"].update(model="model-b", promptVersion=2)
    row = compare_runs(base, candidate)["cases"][0]
    assert row["generation_config_changes"] == {"model": {"before": "model-a", "after": "model-b"}}
    assert "generation_settings_changed" in row["comparison_caveats"]


def test_request_sampling_is_stable_and_rejects_invalid_rates():
    import pytest

    from agent.evaluation import sample_evaluation

    assert sample_evaluation("request-1", "0") is False
    assert sample_evaluation("request-1", "1") is True
    choices = [sample_evaluation(f"request-{i}", "0.2") for i in range(100)]
    assert any(choices) and not all(choices)
    assert choices == [sample_evaluation(f"request-{i}", "0.2") for i in range(100)]
    assert sample_evaluation(None, "1") is False
    for rate in ("nan", "inf", "-0.1", "1.1", "oops"):
        with pytest.raises(ValueError):
            sample_evaluation("request-1", rate)


def test_unsampled_app_request_keeps_content_private(
    fake_openai, stub_docs, span_exporter, monkeypatch
):
    from agent import observability
    from agent.decoder import decode_code

    monkeypatch.setenv("LANGFUSE_EVALUATION_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_EVALUATION_SAMPLE_RATE", "0")
    execution = decode_code("sampling_private = 123", "Beginner")
    observability.flush()
    spans = [
        s
        for s in span_exporter.get_finished_spans()
        if format(s.context.trace_id, "032x") == execution.trace_id
    ]
    assert all("sampling_private" not in str(s.attributes) for s in spans)
    root = next(s for s in spans if s.name == "decode_code")
    assert json.loads(root.attributes["langfuse.observation.metadata.evaluationSampled"]) is False
    assert "langfuse.observation.metadata.evaluationSchema" not in root.attributes
    assert len(fake_openai.requests) == 2


def test_evaluator_receives_only_its_metric_and_shared_instructions():
    from evals.week6.managed import evaluator_definitions

    definitions = evaluator_definitions(["a", "b"], "openai")
    for definition in definitions:
        metric = definition.name.rsplit(".", 1)[1]
        for other in ("semantic_correctness", "evidence_faithfulness", "audience_fit"):
            assert (f"{other}:" in definition.prompt) == (other == metric)
        assert "untrusted DATA" in definition.prompt
        assert "Return exactly one category" in definition.prompt
        assert "{{evidence}}" in definition.prompt and "{{answer}}" in definition.prompt
