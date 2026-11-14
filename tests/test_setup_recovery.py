"""Recover ambiguous setup timeouts without creating duplicate resources."""

from copy import deepcopy
from types import SimpleNamespace as Obj

import pytest

from evals.week6 import managed
from evals.week6.dataset import digest


def test_resume_adopts_committed_resources_and_rejects_definition_drift():
    definitions = managed.evaluator_definitions(["a", "b"], "openai")
    remotes = []
    for i, d in enumerate(definitions):
        payload = d.model_dump(mode="json", by_alias=True, exclude_none=True)
        remote = Obj(id=str(i), name=d.name, version=1, version_id="v1", status="active")
        payload["prompt"] = [{"role": "user", "content": payload["prompt"]}]
        remote.model_dump = lambda payload=payload, **kwargs: deepcopy(payload)
        remotes.append(remote)
    lock = dict(
        protocol="test",
        environment="study",
        models=["a", "b"],
        provider="openai",
        definitions_hash=digest([d.model_dump(mode="json", by_alias=True) for d in definitions]),
        evaluators=[],
        rule_id=None,
        status="creating",
    )
    rule = Obj(
        id="rule",
        name="code-decoder-test",
        enabled=True,
        sampling=1,
        filter=managed.rule_filters("test", "study"),
        evaluator_assignments=[Obj(evaluator_id=r.id, variable_mapping=None) for r in remotes],
    )

    def forbidden_create(**kwargs):
        pytest.fail("a committed remote resource must not be recreated")

    client = Obj(
        api=Obj(
            evaluators=Obj(
                list=lambda **kw: Obj(data=remotes, meta=Obj(cursor=None)),
                get=lambda id: remotes[int(id)],
                create=forbidden_create,
            ),
            evaluation_rules=Obj(
                list=lambda **kw: Obj(data=[rule], meta=Obj(cursor=None)),
                get=lambda id: rule,
                create=forbidden_create,
            ),
        )
    )
    saved = []
    result = managed.resume_setup(
        client, lock, on_progress=lambda value: saved.append(deepcopy(value))
    )
    assert result["status"] == "ready"
    assert len(result["evaluators"]) == 6
    assert result["rule_id"] == "rule"
    assert saved[-1] == result
    remotes[0].model_dump = lambda **kw: {"name": remotes[0].name, "prompt": "edited remotely"}
    with pytest.raises(ValueError, match="definition"):
        managed.resume_setup(client, lock, on_progress=lambda value: None)
