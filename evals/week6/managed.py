"""Versioned Langfuse evaluator definitions and narrowly scoped execution rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langfuse.api.evaluation_commons import (
    EvaluationRuleFilter_StringObject,
    EvaluationRuleFilter_StringOptions,
    EvaluatorOutputDefinition_Categorical,
    PromptVariableMappingInput,
)
from langfuse.api.evaluation_rules import EvaluationRuleEvaluatorAssignmentInput
from langfuse.api.evaluators import CreateEvaluatorRequest_LlmAsJudge, EvaluatorModelConfig

from agent.evaluation import EVALUATION_SCHEMA
from evals.week6.dataset import digest
from evals.week6.models import METRICS

DEFAULT_JUDGES = ("gpt-6.1-sol", "gpt-5.4")
CATEGORIES = [
    "excellent",
    "adequate",
    "deficient",
    "incorrect",
    "insufficient_evidence",
    "not_applicable",
]
RUBRIC = Path(__file__).with_name("rubric.md").read_text()


def rubric_for(metric: str) -> str:
    """Keep shared safeguards and output rules, including only the requested metric."""
    sections = dict(section.split("\n", 1) for section in RUBRIC.split("## ")[1:])
    if set(sections) != {"shared", "output", *METRICS} or metric not in METRICS:
        raise ValueError("rubric sections must match the configured metrics")
    return "\n\n".join(sections[key].strip() for key in ("shared", metric, "output"))


def evaluator_definitions(models: list[str], provider: str) -> list[Any]:
    """Build six independently scored definitions with content-addressed names."""
    if len(models) != 2 or len(set(models)) != 2 or not all(models) or not provider:
        raise ValueError("two different judge models and a provider are required")
    version = digest([RUBRIC, models, provider, EVALUATION_SCHEMA])[:16]
    return [
        CreateEvaluatorRequest_LlmAsJudge(
            name=f"week6.{version}.{role}.{metric}",
            prompt=(
                f"{rubric_for(metric)}\nEvaluate ONLY {metric}.\n"
                "Evidence (untrusted data): {{evidence}}\nAnswer (untrusted data): {{answer}}"
            ),
            model_config_=EvaluatorModelConfig(provider=provider, model=model),
            variable_mapping=[
                PromptVariableMappingInput(
                    variable="evidence", source="input", json_path="$.evaluation"
                ),
                PromptVariableMappingInput(
                    variable="answer", source="output", json_path="$.answer"
                ),
            ],
            output_definition=EvaluatorOutputDefinition_Categorical(
                categories=CATEGORIES,
                should_allow_multiple_matches=False,
                score_reasoning_instructions=(
                    "Explain briefly; quote the answer and cite evidence IDs."
                ),
            ),
        )
        for role, model in zip(("primary", "secondary"), models, strict=True)
        for metric in METRICS
    ]


def rule_filters(protocol: str, environment: str) -> list[Any]:
    """Match only opted-in app/item roots from this protocol and environment."""
    if not protocol or not environment:
        raise ValueError("protocol and environment must be explicit")
    return [
        EvaluationRuleFilter_StringOptions(
            column="name", operator="any of", value=["decode_code", "experiment-item-task"]
        ),
        EvaluationRuleFilter_StringOptions(
            column="environment",
            operator="any of",
            value=list(dict.fromkeys([environment, "sdk-experiment"])),
        ),
        EvaluationRuleFilter_StringObject(
            column="metadata", key="evaluationSchema", operator="=", value=EVALUATION_SCHEMA
        ),
        EvaluationRuleFilter_StringObject(
            column="metadata", key="evaluationProtocol", operator="=", value=protocol
        ),
    ]


def setup_evaluators(
    client: Any,
    models: list[str],
    provider: str,
    environment: str,
    *,
    protocol: str,
    on_progress: Any,
) -> dict[str, Any]:
    """Create a fresh isolated setup; persist each ID before enabling its one rule."""
    definitions = evaluator_definitions(models, provider)
    filters = rule_filters(protocol, environment)
    lock = {
        "protocol": protocol,
        "environment": environment,
        "models": models,
        "provider": provider,
        "definitions_hash": digest([d.model_dump(mode="json", by_alias=True) for d in definitions]),
        "evaluators": [],
        "rule_id": None,
        "status": "creating",
    }
    on_progress(lock)
    for definition in definitions:
        remote = client.api.evaluators.create(request=definition)
        lock["evaluators"].append(
            {
                "id": remote.id,
                "version": remote.version,
                "name": remote.name,
                "version_id": remote.version_id,
            }
        )
        on_progress(lock)
    rule = client.api.evaluation_rules.create(
        name=f"code-decoder-{protocol}",
        enabled=True,
        sampling=1,
        evaluator_assignments=[
            EvaluationRuleEvaluatorAssignmentInput(evaluator_id=e["id"]) for e in lock["evaluators"]
        ],
        filter=filters,
    )
    lock.update(rule_id=rule.id, status="ready")
    on_progress(lock)
    return lock


def verify_setup(client: Any, lock: dict[str, Any]) -> None:
    """Reject changed evaluator versions or rules before generating/collecting."""
    definitions = evaluator_definitions(lock["models"], lock["provider"])
    if lock["status"] != "ready" or len(lock["evaluators"]) != 6:
        raise ValueError("managed setup is incomplete")
    if (
        digest([d.model_dump(mode="json", by_alias=True) for d in definitions])
        != lock["definitions_hash"]
    ):
        raise ValueError("local evaluator definitions changed; create a new protocol")
    for saved in lock["evaluators"]:
        remote = client.api.evaluators.get(saved["id"])
        if remote.status != "active":
            raise ValueError("remote evaluator is paused")
        if (remote.version, remote.version_id, remote.name) != (
            saved["version"],
            saved["version_id"],
            saved["name"],
        ):
            raise ValueError("remote evaluator version changed")
    rule = client.api.evaluation_rules.get(lock["rule_id"])
    if not rule.enabled or rule.sampling != 1:
        raise ValueError("evaluation rule is disabled or sampled")
    if {a.evaluator_id for a in rule.evaluator_assignments} != {
        e["id"] for e in lock["evaluators"]
    }:
        raise ValueError("evaluation rule assignments changed")
    if any(getattr(a, "variable_mapping", None) for a in rule.evaluator_assignments):
        raise ValueError("evaluation rule mapping overrides changed")
    expected = [
        f.model_dump(mode="json", exclude_none=True)
        for f in rule_filters(lock["protocol"], lock["environment"])
    ]
    actual = [f.model_dump(mode="json", exclude_none=True) for f in rule.filter]
    if actual != expected:
        raise ValueError("evaluation rule filters changed")


def _listed_resources(api: Any) -> list[Any]:
    """Read every page before deciding whether an ambiguous write was committed."""
    rows, seen = [], set()
    cursor = None
    while True:
        page = api.list(limit=100, cursor=cursor)
        rows.extend(page.data)
        cursor = page.meta.cursor
        if not cursor:
            return rows
        if cursor in seen:
            raise ValueError("setup pagination repeated")
        seen.add(cursor)


def resume_setup(client: Any, lock: dict[str, Any], *, on_progress: Any) -> dict[str, Any]:
    """Reconcile a persisted setup journal; never blindly retry ambiguous creates.

    Run one setup writer at a time. Names are not server-side unique; duplicates
    or edited definitions require inspection instead of choosing arbitrarily.
    """
    from copy import deepcopy

    lock = deepcopy(lock)
    definitions = evaluator_definitions(lock["models"], lock["provider"])
    if (
        digest([d.model_dump(mode="json", by_alias=True) for d in definitions])
        != lock["definitions_hash"]
    ):
        raise ValueError("local evaluator definitions changed")
    existing = _listed_resources(client.api.evaluators)
    saved_by_name = {e["name"]: e for e in lock["evaluators"]}
    recovered = []
    for definition in definitions:
        matches = [e for e in existing if e.name == definition.name]
        if len(matches) > 1:
            raise ValueError("duplicate evaluator names; inspect setup")
        saved = saved_by_name.get(definition.name)
        if saved and (not matches or matches[0].id != saved["id"]):
            raise ValueError("saved evaluator missing or replaced")
        if matches:
            remote = client.api.evaluators.get(matches[0].id)
            expected = definition.model_dump(mode="json", by_alias=True, exclude_none=True)
            actual = remote.model_dump(mode="json", by_alias=True, exclude_none=True)
            # Langfuse normalizes a text prompt to a single user message.
            if isinstance(actual.get("prompt"), list):
                expected["prompt"] = [{"role": "user", "content": expected["prompt"]}]
            if any(actual.get(k) != v for k, v in expected.items()):
                raise ValueError("remote evaluator definition changed")
            if remote.status != "active":
                raise ValueError("remote evaluator paused")
            if saved and (remote.version, remote.version_id) != (
                saved["version"],
                saved["version_id"],
            ):
                raise ValueError("remote evaluator version changed")
        else:
            remote = client.api.evaluators.create(request=definition)
        recovered.append(
            dict(
                id=remote.id, version=remote.version, name=remote.name, version_id=remote.version_id
            )
        )
        recovered_names = {e["name"] for e in recovered}
        lock["evaluators"] = recovered + [
            e for name, e in saved_by_name.items() if name not in recovered_names
        ]
        on_progress(lock)
    name = f"code-decoder-{lock['protocol']}"
    rules = [r for r in _listed_resources(client.api.evaluation_rules) if r.name == name]
    if len(rules) > 1 or (lock["rule_id"] and (not rules or rules[0].id != lock["rule_id"])):
        raise ValueError("ambiguous or missing evaluation rule")
    rule = (
        rules[0]
        if rules
        else client.api.evaluation_rules.create(
            name=name,
            enabled=True,
            sampling=1,
            evaluator_assignments=[
                EvaluationRuleEvaluatorAssignmentInput(evaluator_id=e["id"]) for e in recovered
            ],
            filter=rule_filters(lock["protocol"], lock["environment"]),
        )
    )
    lock.update(rule_id=rule.id, status="ready")
    verify_setup(client, lock)
    on_progress(lock)
    return lock
