"""Account only for judge executions linked to the requested run."""

from types import SimpleNamespace as Obj


def test_usage_links_target_and_rule_and_keeps_missing_cost_unknown():
    from evals.week6.usage import collect_usage

    def row(id, target, cost, rule="rule"):
        return Obj(
            id=id,
            trace_id="judge-" + id,
            type="GENERATION",
            model="judge",
            metadata={
                "target_observation_id": target,
                "target_trace_id": "trace",
                "evaluation_rule_id": rule,
            },
            usage_details={"input": 100, "output": 10, "total": 110},
            total_cost=cost,
        )

    rows = [
        row("1", "target", 0.1),
        row("2", "target", None),
        row("3", "other", 9),
        row("4", "target", 9, "other"),
    ]
    client = Obj(
        api=Obj(observations=Obj(get_many=lambda **kw: Obj(data=rows, meta=Obj(cursor=None))))
    )
    artifact = {
        "started_at": "2026-11-08T00:00:00+00:00",
        "setup": {"rule_id": "rule"},
        "records": [
            {
                "outcome": "success",
                "evaluation_observation_id": "target",
                "evaluation_trace_id": "trace",
            }
        ],
    }
    result = collect_usage(client, artifact)
    assert result["executions"] == 2
    assert result["models"]["judge"]["total_tokens"] == 220
    assert result["known_cost_usd"] == 0.1
    assert result["missing_cost_executions"] == 1
    assert result["total_cost_usd"] is None


def test_partial_execution_cost_is_not_a_complete_total():
    from evals.week6.usage import collect_usage

    row = Obj(
        id="one",
        trace_id="judge",
        model="judge",
        metadata={
            "target_trace_id": "t",
            "target_observation_id": "o",
            "evaluation_rule_id": "r",
            "evaluator_id": "e",
        },
        usage_details={},
        total_cost=0.01,
    )
    client = Obj(
        api=Obj(observations=Obj(get_many=lambda **kw: Obj(data=[row], meta=Obj(cursor=None))))
    )
    artifact = {
        "started_at": "2026-11-08T00:00:00+00:00",
        "setup": {"rule_id": "r", "evaluators": [{"id": "e"}, {"id": "missing"}]},
        "records": [
            {"outcome": "success", "evaluation_trace_id": "t", "evaluation_observation_id": "o"}
        ],
    }
    result = collect_usage(client, artifact)
    assert result["total_cost_usd"] is None
    assert result["known_cost_usd"] == 0.01
    assert result["missing_evaluator_targets"] == 1
    assert result["models"]["judge"]["missing_usage_executions"] == 1
