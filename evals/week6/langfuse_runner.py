"""Native Langfuse SDK experiments: decode and judge inside the real experiment."""

import asyncio
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from agent.evaluation import EVALUATION_SCHEMA
from evals.week6.dataset import dataset_digest, load_cases
from evals.week6.experiment import run_case
from evals.week6.models import EvalCase


def sync_dataset(client: Any, cases: list[EvalCase], *, controls: bool = False) -> list[Any]:
    if controls:
        from evals.week6.controls import load_controls

        approved = {c["case"]["case_id"]: c["case"] for c in load_controls()}
    else:
        approved = {c.case_id: c.model_dump() for c in load_cases()}
    if not cases or any(approved.get(c.case_id) != c.model_dump() for c in cases):
        raise ValueError("managed dataset accepts only unchanged shipped synthetic cases")
    name = f"week6/code-decoder/{dataset_digest(cases)[:16]}"
    client.create_dataset(name=name, description="Synthetic code explanation evaluation")
    items = []
    for case in cases:
        item = client.create_dataset_item(
            dataset_name=name,
            id=str(uuid5(NAMESPACE_URL, f"{name}/{case.case_id}")),
            input=case.model_dump(),
            expected_output={
                "outcome": case.expected_outcome,
                "facts": case.facts,
                "forbidden_claims": case.forbidden_claims,
            },
            metadata={"split": case.split, "level": case.level},
        )
        # Do not trust a remotely edited item as permission to export other content.
        if item.input != case.model_dump():
            raise ValueError("remote dataset differs from shipped synthetic case")
        items.append(item)
    return items


def run_experiment(
    client: Any,
    cases: list[EvalCase],
    *,
    run_name: str,
    data: list[Any],
    metadata: dict[str, Any],
    on_record: Any = None,
    execute_case: Any = run_case,
) -> tuple[Any, list[dict[str, Any]]]:
    """Run the app and publish one eligible item root; judges run on Langfuse."""
    approved = {c.case_id: c.model_dump() for c in cases}
    records = []

    async def task(*, item):
        payload = item["input"] if isinstance(item, dict) else item.input
        case = EvalCase.model_validate(payload)
        if approved.get(case.case_id) != payload:
            raise ValueError("experiment item mismatch")
        record = await asyncio.to_thread(execute_case, case)
        record["evaluation_observation_id"] = client.get_current_observation_id()
        record["evaluation_trace_id"] = client.get_current_trace_id()
        if record["outcome"] == "success":
            client.update_current_span(
                input={"evaluation": record["evaluation"]},
                metadata={"evaluationSchema": EVALUATION_SCHEMA, **metadata},
            )
        records.append(record)
        if on_record:
            on_record(record)
        # SDK records this return value on the item root after task completion.
        return {"answer": record["answer"], "outcome": record["outcome"]}

    result = client.run_experiment(
        name="week6-code-decoder",
        run_name=run_name,
        data=data,
        task=task,
        max_concurrency=1,
        metadata={},
    )
    if len(result.item_results) != len(cases) or len(records) != len(cases):
        raise RuntimeError("incomplete experiment; inspect saved partial records")
    if any(not r["evaluation_observation_id"] for r in records):
        raise RuntimeError("missing evaluation observation linkage")
    client.flush()
    return result, records
