"""Shared fixtures: a mocked OpenAI Responses API and an in-memory Langfuse export."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
import pytest
from openai import AsyncOpenAI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agents import set_default_openai_client

CANARY = "canary_xyz"

USAGE = {
    "input_tokens": 1200,
    "output_tokens": 80,
    "total_tokens": 1280,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens_details": {"reasoning_tokens": 0},
}


def tool_call_response() -> list[dict[str, Any]]:
    return [
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "decode_code_pipeline",
            "arguments": "{}",
            "status": "completed",
        }
    ]


def message_response(text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]


def decode_result_json(**overrides: Any) -> str:
    body = {
        "what": [f"{CANARY} 결과를 json.dumps로 직렬화합니다"],
        "why": "설명",
        "source": [],
        "example": "print(1)",
        "check": "무엇을 반환할까요?",
        "concepts": [],
        "quiz": {
            "question": "인자를 바꾸면 무엇이 달라질까요?",
            "options": [
                {"label": "출력 문자열", "correct": True, "feedback": "직렬화 결과가 바뀝니다."},
                {"label": "아무것도", "correct": False, "feedback": "인자가 결과에 쓰입니다."},
            ],
        },
    }
    body.update(overrides)
    return json.dumps(body, ensure_ascii=False)


@dataclass
class FakeOpenAI:
    """Mocked Responses API: first call returns the tool call, second the answer."""

    final_text: str = field(default_factory=decode_result_json)
    requests: list[str] = field(default_factory=list)
    bodies: list[dict[str, Any]] = field(default_factory=list)
    error_status: int | None = None  # respond with an API error whose body has the canary

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        body = json.loads(request.content or b"{}")
        self.bodies.append(body)
        if self.error_status is not None:
            return httpx.Response(
                self.error_status,
                json={"error": {"message": f"{CANARY}_api_error echoing input", "type": "invalid_request_error", "code": "x"}},
            )
        has_tool_output = any(
            isinstance(item, dict) and item.get("type") == "function_call_output"
            for item in body.get("input", [])
        )
        output = message_response(self.final_text) if has_tool_output else tool_call_response()
        return httpx.Response(
            200,
            json={
                "id": f"resp_{len(self.requests)}",
                "object": "response",
                "created_at": 0,
                "model": "gpt-4.1-mini",
                "status": "completed",
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
                "usage": USAGE,
                "output": output,
            },
        )


@pytest.fixture
def fake_openai() -> FakeOpenAI:
    fake = FakeOpenAI()
    set_default_openai_client(
        AsyncOpenAI(
            api_key="sk-test",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
        )
    )
    return fake


@pytest.fixture(scope="session")
def span_exporter() -> InMemorySpanExporter:
    """Enable tracing once per test session with an in-memory export target."""
    os.environ.update(
        {
            "LANGFUSE_ENABLED": "1",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_BASE_URL": "http://127.0.0.1:9",
            "LANGFUSE_TRACING_ENVIRONMENT": "test",
            "LANGFUSE_CAPTURE_CONTENT": "1",  # requested, but must be forced off outside local
        }
    )
    from agent import observability

    exporter = InMemorySpanExporter()
    settings = observability.init_observability(span_exporter=exporter)
    assert settings.enabled and not settings.capture_content
    return exporter


@pytest.fixture
def stub_docs(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, str]], None]:
    """Replace network documentation lookup with fixed statuses per module."""
    from agent import pipeline
    from agent.models import DocumentationEvidence

    statuses: dict[str, str] = {}

    def lookup(module: str, symbol: str) -> DocumentationEvidence:
        status = statuses.get(module, "unsupported")
        public = status != "unsupported"
        return DocumentationEvidence(
            source_id=f"source-{module}" if public else "",
            status=status,
            module=module,
            symbol=symbol,
            title=f"Python documentation: {module}.{symbol}" if public else "",
            excerpt="excerpt" if status == "exact_match" else "",
            url=f"https://docs.python.org/3/library/{module}.html" if public else "",
            error_type="TimeoutError" if status == "unavailable" else None,
        )

    monkeypatch.setattr(pipeline, "lookup_documentation", lookup)
    return statuses.update


@pytest.fixture
def scores(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Record scores sent through the observability wrapper as (name, value)."""
    from agent import observability

    recorded: list[tuple[str, Any]] = []
    original = observability.Observation.score

    def spy(self: Any, name: str, value: Any) -> None:
        recorded.append((name, value))
        original(self, name, value)

    monkeypatch.setattr(observability.Observation, "score", spy)
    return recorded


def make_text_prompt(*, template: str | None = None, config: Any = None, version: int = 3):
    """Build a Langfuse text prompt client as returned by get_prompt."""
    from langfuse.api.prompts.types.prompt import Prompt_Text
    from langfuse.model import TextPromptClient

    from agent.prompts import LOCAL_PROMPT_CONFIG, LOCAL_SYSTEM_PROMPT_TEMPLATE, PROMPT_NAME

    return TextPromptClient(
        Prompt_Text(
            name=PROMPT_NAME,
            version=version,
            prompt=template if template is not None else LOCAL_SYSTEM_PROMPT_TEMPLATE,
            config=config if config is not None else LOCAL_PROMPT_CONFIG,
            labels=["production"],
            tags=[],
        )
    )


@pytest.fixture
def prompt_fetch(monkeypatch: pytest.MonkeyPatch, span_exporter: InMemorySpanExporter):
    """Control what the Langfuse client returns from get_prompt (no network)."""
    from agent import observability

    behavior: dict[str, Any] = {"result": RuntimeError("prompt API unavailable")}

    def get_prompt(*_: Any, **__: Any) -> Any:
        result = behavior["result"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(observability._state.client, "get_prompt", get_prompt)
    return behavior
