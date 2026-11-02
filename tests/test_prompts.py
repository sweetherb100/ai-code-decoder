"""Prompt resolution: remote prompt, atomic fallback, and the inference bundle."""

from __future__ import annotations

from typing import Any

import pytest

from agent.observability_fields import PROMPT_FALLBACK_REASONS
from agent.prompts import (
    DEFAULT_MODEL,
    LEVEL_STYLES,
    LOCAL_PROMPT_CONFIG,
    LOCAL_PROMPT_VERSION,
    PROMPT_SCHEMA_VERSION,
    InferenceConfig,
    instructions_for_level,
    resolve_instructions,
)
from tests.conftest import make_text_prompt


class FakeClient:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def get_prompt(self, name: str, **kwargs: Any) -> Any:
        self.calls.append({"name": name, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture(autouse=True)
def no_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


def config(**overrides: Any) -> dict[str, Any]:
    return {**LOCAL_PROMPT_CONFIG, **overrides}


def without(*keys: str) -> dict[str, Any]:
    return {k: v for k, v in LOCAL_PROMPT_CONFIG.items() if k not in keys}


def resolve(prompt_config: Any = None, **prompt_kwargs: Any):
    prompt = make_text_prompt(config=prompt_config, **prompt_kwargs)
    return resolve_instructions("Beginner", FakeClient(prompt), "production")


def test_remote_prompt_is_used_with_its_config():
    custom = config(model="gpt-4.1", levelStyles={**LEVEL_STYLES, "Developer": "Be terse."})
    client = FakeClient(make_text_prompt(config=custom, version=5))
    resolved = resolve_instructions("Developer", client, "staging")
    assert resolved.source == "langfuse"
    assert resolved.version == "5"
    assert resolved.instructions.endswith("Audience level: Developer. Be terse.")
    assert resolved.inference == InferenceConfig(model="gpt-4.1", source="prompt_config")
    assert resolved.remote is client.result
    call = client.calls[0]
    assert call["label"] == "staging" and call["type"] == "text"
    assert call["max_retries"] == 1 and call["fetch_timeout_seconds"] == 2


def test_disabled_telemetry_uses_local_prompt():
    resolved = resolve_instructions("Beginner", None, "production")
    assert resolved.source == "fallback"
    assert resolved.fallback_reason == "disabled"
    assert resolved.instructions == instructions_for_level("Beginner")
    assert resolved.version == LOCAL_PROMPT_VERSION
    assert resolved.inference == InferenceConfig(model=DEFAULT_MODEL, source="default")


def _fallback_prompt():
    prompt = make_text_prompt()
    prompt.is_fallback = True
    return prompt


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (_fallback_prompt(), "fetch_failed"),
        (RuntimeError("boom"), "unexpected"),
        (
            make_text_prompt(config=config(schemaVersion=PROMPT_SCHEMA_VERSION + 1)),
            "schema_mismatch",
        ),
        (make_text_prompt(config={"model": "x"}), "schema_mismatch"),
        (make_text_prompt(config=config(levelStyles={"Beginner": "only one"})), "invalid_config"),
        (make_text_prompt(config=config(model="")), "invalid_config"),
        (make_text_prompt(config=["not", "a", "dict"]), "invalid_config"),
        (make_text_prompt(config=config(temperature="0.2")), "invalid_config"),
        (make_text_prompt(config=config(temperature=True)), "invalid_config"),
        (make_text_prompt(config=config(temperature=-0.1)), "invalid_config"),
        (make_text_prompt(config=config(temperature=2.5)), "invalid_config"),
        (make_text_prompt(config=config(reasoningEffort="extreme")), "invalid_config"),
        (make_text_prompt(config=config(reasoningEffort=3)), "invalid_config"),
        (make_text_prompt(template="No variables here"), "compile_failed"),
        (make_text_prompt(template="{{level}} {{level_style}} {{extra}}"), "compile_failed"),
    ],
)
def test_any_failure_falls_back_to_the_whole_local_prompt(result, reason):
    resolved = resolve_instructions("Beginner", FakeClient(result), "production")
    assert resolved.source == "fallback"
    assert resolved.fallback_reason == reason
    assert reason in PROMPT_FALLBACK_REASONS
    # Never a mix: local instructions, local version, no link, default inference.
    assert resolved.instructions == instructions_for_level("Beginner")
    assert resolved.version == LOCAL_PROMPT_VERSION
    assert resolved.remote is None
    assert resolved.inference == InferenceConfig(model=DEFAULT_MODEL, source="default")


def test_chat_prompt_is_a_type_mismatch():
    class ChatLike:
        is_fallback = False
        prompt = [{"role": "system", "content": "x"}]
        config = LOCAL_PROMPT_CONFIG

    resolved = resolve_instructions("Beginner", FakeClient(ChatLike()), "production")
    assert resolved.fallback_reason == "type_mismatch"


def test_fallback_version_identifies_the_local_template():
    assert LOCAL_PROMPT_VERSION.startswith("fallback-")
    assert len(LOCAL_PROMPT_VERSION) == len("fallback-") + 12


@pytest.mark.parametrize(
    ("prompt_config", "temperature", "effort"),
    [
        (config(temperature=0.2), 0.2, None),
        (config(temperature=0), 0.0, None),
        (config(temperature=2), 2.0, None),
        (config(temperature=None), None, None),
        (without("temperature"), None, None),  # missing -> provider default, not sent
        (config(reasoningEffort="low"), None, "low"),
        (config(reasoningEffort="high", temperature=1), 1.0, "high"),
    ],
)
def test_parameters_come_from_prompt_config(prompt_config, temperature, effort):
    resolved = resolve(prompt_config)
    assert resolved.source == "langfuse"
    assert resolved.inference.source == "prompt_config"
    assert (resolved.inference.temperature, resolved.inference.reasoning_effort) == (
        temperature,
        effort,
    )


@pytest.mark.parametrize(
    "prompt_config",
    [
        config(model="reasoning-model", reasoningEffort="high", temperature=None),
        config(model="gpt-4.1-mini", temperature=1.0),
    ],
)
def test_env_model_override_drops_prompt_parameters(monkeypatch, prompt_config):
    """OPENAI_MODEL replaces the whole bundle; it never inherits another model's params."""
    monkeypatch.setenv("OPENAI_MODEL", "some-other-model")
    resolved = resolve(prompt_config)
    assert resolved.source == "langfuse"  # the prompt text is still the remote one
    assert resolved.inference == InferenceConfig(model="some-other-model", source="env")
