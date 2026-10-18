"""Prompt resolution: remote prompt, atomic fallback, and model precedence."""

from __future__ import annotations

from typing import Any

import pytest

from agent.prompts import (
    LEVEL_STYLES,
    LOCAL_PROMPT_CONFIG,
    LOCAL_PROMPT_VERSION,
    PROMPT_SCHEMA_VERSION,
    instructions_for_level,
    resolve_instructions,
)
from agent.observability_fields import PROMPT_FALLBACK_REASONS
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


def test_remote_prompt_is_used_with_its_config():
    custom = config(model="gpt-4.1", levelStyles={**LEVEL_STYLES, "Developer": "Be terse."})
    client = FakeClient(make_text_prompt(config=custom, version=5))
    resolved = resolve_instructions("Developer", client, "staging")
    assert resolved.source == "langfuse"
    assert resolved.version == "5"
    assert resolved.instructions.endswith("Audience level: Developer. Be terse.")
    assert (resolved.model, resolved.model_source) == ("gpt-4.1", "prompt_config")
    assert resolved.remote is client.result
    call = client.calls[0]
    assert call["label"] == "staging" and call["type"] == "text"
    assert call["max_retries"] == 1 and call["fetch_timeout_seconds"] == 2


def test_env_model_overrides_prompt_config(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-env")
    resolved = resolve_instructions("Beginner", FakeClient(make_text_prompt()), "production")
    assert (resolved.model, resolved.model_source) == ("gpt-env", "env")


def test_disabled_telemetry_uses_local_prompt():
    resolved = resolve_instructions("Beginner", None, "production")
    assert resolved.source == "fallback"
    assert resolved.fallback_reason == "disabled"
    assert resolved.instructions == instructions_for_level("Beginner")
    assert resolved.version == LOCAL_PROMPT_VERSION
    assert (resolved.model, resolved.model_source) == ("gpt-4.1-mini", "default")


def _fallback_prompt():
    prompt = make_text_prompt()
    prompt.is_fallback = True
    return prompt


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (_fallback_prompt(), "fetch_failed"),
        (RuntimeError("boom"), "unexpected"),
        (make_text_prompt(config=config(schemaVersion=PROMPT_SCHEMA_VERSION + 1)), "schema_mismatch"),
        (make_text_prompt(config={"model": "x"}), "schema_mismatch"),
        (make_text_prompt(config=config(levelStyles={"Beginner": "only one"})), "invalid_config"),
        (make_text_prompt(config=config(model="")), "invalid_config"),
        (make_text_prompt(config=["not", "a", "dict"]), "invalid_config"),
        (make_text_prompt(template="No variables here"), "compile_failed"),
        (make_text_prompt(template="{{level}} {{level_style}} {{extra}}"), "compile_failed"),
    ],
)
def test_any_failure_falls_back_to_the_whole_local_prompt(result, reason):
    resolved = resolve_instructions("Beginner", FakeClient(result), "production")
    assert resolved.source == "fallback"
    assert resolved.fallback_reason == reason
    assert reason in PROMPT_FALLBACK_REASONS
    # Never a mix: local instructions, local version, no prompt link.
    assert resolved.instructions == instructions_for_level("Beginner")
    assert resolved.version == LOCAL_PROMPT_VERSION
    assert resolved.remote is None


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
