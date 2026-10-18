"""Unit tests for telemetry settings, fail-open behavior, and the field registry."""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from agent import observability
from agent.observability import Observation, load_settings, observation
from agent.observability_fields import ROOT_METADATA_KEYS, is_allowed_attribute

CREDENTIALS = {
    "LANGFUSE_PUBLIC_KEY": "pk",
    "LANGFUSE_SECRET_KEY": "sk",
    "LANGFUSE_BASE_URL": "http://localhost",
}


def test_enabled_requires_flag_and_all_credentials():
    assert not load_settings({}).enabled
    assert not load_settings(CREDENTIALS).enabled
    partial = {"LANGFUSE_ENABLED": "1", "LANGFUSE_PUBLIC_KEY": "pk"}
    assert not load_settings(partial).enabled
    assert load_settings(partial).missing_credentials
    assert load_settings({**CREDENTIALS, "LANGFUSE_ENABLED": "1"}).enabled


def test_content_capture_is_forced_off_outside_local():
    local = load_settings({"LANGFUSE_CAPTURE_CONTENT": "1"})
    assert local.capture_content and not local.capture_forced_off
    remote = load_settings(
        {"LANGFUSE_CAPTURE_CONTENT": "1", "LANGFUSE_TRACING_ENVIRONMENT": "production"}
    )
    assert not remote.capture_content and remote.capture_forced_off


def test_sample_rate_defaults_to_full_collection():
    assert load_settings({}).sample_rate == 1.0
    assert load_settings({"LANGFUSE_SAMPLE_RATE": "not-a-number"}).sample_rate == 1.0


def test_metadata_keys_are_langfuse_safe():
    assert all(re.fullmatch(r"[a-z][A-Za-z0-9]*", key) for key in ROOT_METADATA_KEYS)


def test_attribute_allowlist():
    assert is_allowed_attribute("llm.token_count.prompt", capture_content=False)
    assert is_allowed_attribute("langfuse.observation.level", capture_content=False)
    assert not is_allowed_attribute("input.value", capture_content=False)
    assert not is_allowed_attribute("tool.parameters", capture_content=False)
    assert not is_allowed_attribute("some.new.attribute", capture_content=False)
    assert is_allowed_attribute("input.value", capture_content=True)
    assert not is_allowed_attribute("some.new.attribute", capture_content=True)


def test_unknown_metadata_keys_are_dropped(caplog):
    with caplog.at_level("WARNING", logger="agent.observability"):
        accepted = observability.root_metadata({"outcome": "success", "rawCode": "x"})
    assert accepted == {"outcome": "success"}
    assert "telemetry_unknown_metadata_key key=rawCode" in caplog.text


class _BrokenSpan:
    def update(self, **_):
        raise RuntimeError("langfuse down")

    def score(self, **_):
        raise RuntimeError("langfuse down")


def test_observation_wrapper_is_fail_open():
    span = Observation(_BrokenSpan())
    span.update(output={"a": 1})
    span.score("grounding_passed", True)


def test_observation_reraises_the_original_exception():
    error = ValueError("secret code text")
    with pytest.raises(ValueError) as raised:
        with observation("unit", expected={ValueError: ("WARNING", "input_rejected")}):
            raise error
    assert raised.value is error


def test_classification_never_uses_exception_message():
    assert observability._classify(KeyError("secret"), {}, None) == ("ERROR", "KeyError")
    assert observability._classify(KeyError("secret"), {}, "runtime_error") == (
        "ERROR",
        "runtime_error:KeyError",
    )


def test_disabled_mode_creates_no_agent_traces():
    """Run in a fresh process because tracing configuration is process-global."""
    script = textwrap.dedent(
        """
        import os
        os.environ.update({"LANGFUSE_ENABLED": "0", "OPENAI_API_KEY": "sk-test"})
        import pytest  # noqa: F401
        from tests.conftest import FakeOpenAI
        import httpx
        from openai import AsyncOpenAI
        from agents import set_default_openai_client
        from agents.tracing import get_trace_provider

        fake = FakeOpenAI()
        set_default_openai_client(AsyncOpenAI(api_key="sk-test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))))
        import agent.pipeline as pipeline
        from agent.models import DocumentationEvidence
        pipeline.lookup_documentation = lambda m, s: DocumentationEvidence(
            source_id="", status="unsupported", module=m, symbol=s, title="", excerpt="", url="")
        from agent.decoder import decode_code
        execution = decode_code("print(len('a'))", "Beginner")
        assert execution.trace_id is None
        assert get_trace_provider()._disabled
        assert set(fake.requests) == {"/v1/responses"}, fake.requests
        print("ok")
        """
    )
    root = Path(__file__).resolve().parent.parent
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=root, capture_output=True, text=True, timeout=120
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip().endswith("ok")


def test_score_values_follow_registered_types():
    assert observability._score_value("grounding_passed", False) == ("BOOLEAN", 0.0)
    assert observability._score_value("cited_source_count", 2) == ("NUMERIC", 2.0)
    assert observability._score_value("grounding_issue", "missing_field") == (
        "CATEGORICAL",
        "missing_field",
    )
    with pytest.raises(KeyError):
        observability._score_value("made_up_score", 1)


def test_representative_grounding_issue_uses_priority():
    from agent.decoder import _representative_issue

    assert _representative_issue(("missing_source", "unverified_source")) == "unverified_source"
    assert _representative_issue(("missing_field", "duplicate_source")) == "missing_field"


def test_user_feedback_uses_a_stable_score_id(monkeypatch):
    calls = []

    class Client:
        def create_score(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(observability, "_state", observability._State(settings=load_settings({}), client=Client()))
    observability.record_user_feedback("t1", "o1", positive=True)
    observability.record_user_feedback("t1", "o1", positive=False)
    assert [c["score_id"] for c in calls] == ["t1-user_feedback", "t1-user_feedback"]
    assert [c["value"] for c in calls] == [1.0, 0.0]
    assert calls[0]["data_type"] == "BOOLEAN" and calls[0]["observation_id"] == "o1"


def test_user_feedback_without_trace_is_ignored(monkeypatch):
    monkeypatch.setattr(observability, "_state", None)
    observability.record_user_feedback(None, None, positive=True)
