"""End-to-end tracing invariants with the real Agents SDK, OpenInference, and Langfuse.

OpenAI is mocked at the HTTP layer and Langfuse exports to memory, so these tests
check the exact span payload that would leave the process.
"""

from __future__ import annotations

import json
import logging

import pytest
from agents.exceptions import ModelBehaviorError
from openai import APIStatusError

from agent import observability
from agent.analyzer import CodeAnalysisError
from agent.decoder import decode_code
from agent.observability_fields import (
    OUTCOMES,
    ROOT_METADATA_KEYS,
    ROOT_OBSERVATION_NAME,
    is_allowed_attribute,
)
from agent.quality import DecodeQualityError
from tests.conftest import CANARY, decode_result_json

CODE = (
    f"from {CANARY}_pkg.billing import {CANARY}_sym\n"
    "import json\n"
    f"payload = json.dumps({{'{CANARY}_key': 1}})\n"
    f"{CANARY}_sym(payload)\n"
)
OI_SCOPE = "openinference.instrumentation.openai_agents"


def export(exporter):
    observability.flush()
    spans = exporter.get_finished_spans()
    exporter.clear()
    return spans


def attr(span, key):
    return (span.attributes or {}).get(key)


def root_of(spans):
    roots = [
        s
        for s in spans
        if s.name == ROOT_OBSERVATION_NAME and s.instrumentation_scope.name == "langfuse-sdk"
    ]
    assert len(roots) == 1
    return roots[0]


def root_metadata(span):
    prefix = "langfuse.observation.metadata."
    return {
        k[len(prefix) :]: json.loads(v)
        for k, v in (span.attributes or {}).items()
        if k.startswith(prefix)
    }


def is_descendant(span, ancestor, by_id):
    current = span
    while current.parent is not None:
        current = by_id.get(current.parent.span_id)
        if current is None:
            return False
        if current.context.span_id == ancestor.context.span_id:
            return True
    return False


def assert_no_canary(spans):
    leaks = []
    for span in spans:
        if CANARY in span.name:
            leaks.append((span.name, "name"))
        if span.status.description and CANARY in span.status.description:
            leaks.append((span.name, "status"))
        for key, value in (span.attributes or {}).items():
            if CANARY in str(value):
                leaks.append((span.name, key))
        for event in span.events:
            if CANARY in event.name or CANARY in json.dumps(
                dict(event.attributes or {}), default=str
            ):
                leaks.append((span.name, f"event:{event.name}"))
    assert leaks == []


def assert_allowlisted(spans):
    extra = {
        (span.instrumentation_scope.name, key)
        for span in spans
        for key in (span.attributes or {})
        if not is_allowed_attribute(key, capture_content=False)
    }
    assert extra == set()


def assert_no_exception_events(spans):
    assert [(s.name, e.name) for s in spans for e in s.events if e.name == "exception"] == []


def test_success_trace_invariants(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, caplog
):
    stub_docs({"json": "exact_match"})
    fake_openai.final_text = decode_result_json(
        source=[
            {
                "source_id": "source-json",
                "title": "Python documentation: json.dumps",
                "url": "https://docs.python.org/3/library/json.html",
            }
        ]
    )
    with caplog.at_level(logging.WARNING, logger="agent.observability"):
        execution = decode_code(CODE, "Beginner", session_id="session-1")
    spans = export(span_exporter)
    by_id = {s.context.span_id: s for s in spans}
    root = root_of(spans)

    # One trace, everything under the manual root.
    assert {s.context.trace_id for s in spans} == {root.context.trace_id}
    assert all(s is root or is_descendant(s, root, by_id) for s in spans)

    llm_spans = [s for s in spans if attr(s, "openinference.span.kind") == "LLM"]
    tool_spans = [s for s in spans if attr(s, "openinference.span.kind") == "TOOL"]
    assert len(llm_spans) == len(fake_openai.requests) == 2
    assert len(tool_spans) == 1
    for name in ("build_learning_plan", "lookup_documentation"):
        manual = [s for s in spans if s.name == name]
        assert manual and all(is_descendant(s, tool_spans[0], by_id) for s in manual)

    # Only Langfuse receives traces; OpenAI only sees model calls.
    assert set(fake_openai.requests) == {"/v1/responses"}

    metadata = root_metadata(root)
    assert metadata["outcome"] == "success"
    assert set(metadata) <= set(ROOT_METADATA_KEYS)
    assert metadata["llmCallCount"] == 2
    assert metadata["contentCaptured"] is False
    assert ("tool_contract_passed", True) in scores and (
        "citation_integrity_passed",
        True,
    ) in scores
    assert execution.trace_id == format(root.context.trace_id, "032x")

    assert_no_canary(spans)
    assert_allowlisted(spans)
    assert_no_exception_events(spans)
    assert "telemetry_unknown_metadata_key" not in caplog.text


def test_unsupported_target_names_are_not_exported(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "exact_match"})
    decode_code(f"import {CANARY}_mod\n{CANARY}_mod.run()\n", "Developer")
    spans = export(span_exporter)
    lookups = [s for s in spans if s.name == "lookup_documentation"]
    assert lookups
    for span in lookups:
        output = json.loads(attr(span, "langfuse.observation.output"))
        assert output["status"] == "unsupported"
        assert CANARY not in str(attr(span, "langfuse.observation.input"))
    assert_no_canary(spans)


def test_syntax_error_is_input_rejected_without_llm_calls(
    span_exporter, prompt_fetch, fake_openai, scores
):
    with pytest.raises(CodeAnalysisError):
        decode_code(f"{CANARY}_value = (\n", "Beginner")
    spans = export(span_exporter)
    root = root_of(spans)
    assert attr(root, "langfuse.observation.level") == "WARNING"
    assert attr(root, "langfuse.observation.status_message") == "input_rejected"
    assert root_metadata(root)["outcome"] == "input_rejected"
    assert fake_openai.requests == []
    assert not [s for s in spans if s.instrumentation_scope.name != "langfuse-sdk"]
    assert scores == []
    assert_no_canary(spans)
    assert_no_exception_events(spans)


def test_unparseable_model_output_is_agent_behavior_failure(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    fake_openai.final_text = f'{{"what": ["{CANARY}_model_output"'
    with pytest.raises(ModelBehaviorError):
        decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    root = root_of(spans)
    assert root_metadata(root)["outcome"] == "agent_behavior_failed"
    assert attr(root, "langfuse.observation.level") == "ERROR"
    assert scores == []  # validation never ran, so no pass score is created
    assert_no_canary(spans)
    assert_no_exception_events(spans)


def test_grounding_failure_records_false_score_and_issue_code(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "exact_match"})
    fake_openai.final_text = decode_result_json(
        source=[{"source_id": "source-made-up", "title": "t", "url": "https://example.com"}]
    )
    with pytest.raises(DecodeQualityError):
        decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    root = root_of(spans)
    assert root_metadata(root)["outcome"] == "citation_integrity_failed"
    grounding = next(s for s in spans if s.name == "validate_output.citation_integrity")
    assert attr(grounding, "langfuse.observation.level") == "ERROR"
    assert attr(grounding, "langfuse.observation.status_message") == "citation_integrity_failed"
    assert json.loads(attr(grounding, "langfuse.observation.output"))["issueCodes"] == [
        "unverified_source"
    ]
    assert ("tool_contract_passed", True) in scores
    assert ("citation_integrity_passed", False) in scores
    assert_no_exception_events(spans)


def test_outcomes_are_registered():
    from agent.decoder import OUTCOME_BY_ERROR

    assert {outcome for _, outcome in OUTCOME_BY_ERROR.values()} | {
        "success",
        "runtime_error",
    } == OUTCOMES


def test_unavailable_docs_are_warnings_with_error_type(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "unavailable"})
    decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    lookup = next(s for s in spans if s.name == "lookup_documentation")
    assert attr(lookup, "langfuse.observation.level") == "WARNING"
    assert json.loads(attr(lookup, "langfuse.observation.output"))["errorType"] == "TimeoutError"
    assert root_metadata(root_of(spans))["docsUnavailableCount"] == 1


def test_remote_prompt_is_linked_to_every_generation(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    from tests.conftest import make_text_prompt

    prompt_fetch["result"] = make_text_prompt(version=7)
    decode_code(CODE, "Developer")
    spans = export(span_exporter)
    generations = [s for s in spans if attr(s, "openinference.span.kind") == "LLM"]
    assert len(generations) == 2
    for span in generations:
        assert attr(span, "langfuse.observation.prompt.name") == "code-decoder/system"
        assert attr(span, "langfuse.observation.prompt.version") == 7
    metadata = root_metadata(root_of(spans))
    assert metadata["promptSource"] == "langfuse"
    assert metadata["promptVersion"] == "7"
    assert "promptFallbackReason" not in metadata
    resolve = next(s for s in spans if s.name == "prompt.resolve")
    assert attr(resolve, "langfuse.observation.level") in (None, "DEFAULT")


def test_prompt_fetch_failure_falls_back_without_link(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    from agent.prompts import LOCAL_PROMPT_VERSION

    execution = decode_code(CODE, "Beginner")
    assert execution.result.what
    spans = export(span_exporter)
    generations = [s for s in spans if attr(s, "openinference.span.kind") == "LLM"]
    assert generations
    assert all(attr(s, "langfuse.observation.prompt.name") is None for s in generations)
    metadata = root_metadata(root_of(spans))
    assert metadata["promptSource"] == "fallback"
    assert metadata["promptVersion"] == LOCAL_PROMPT_VERSION
    assert metadata["promptFallbackReason"] == "unexpected"
    resolve = next(s for s in spans if s.name == "prompt.resolve")
    assert attr(resolve, "langfuse.observation.level") == "WARNING"


def test_answer_quality_scores(span_exporter, prompt_fetch, fake_openai, stub_docs, scores):
    stub_docs({"json": "exact_match"})
    fake_openai.final_text = decode_result_json(
        source=[
            {
                "source_id": "source-json",
                "title": "Python documentation: json.dumps",
                "url": "https://docs.python.org/3/library/json.html",
            }
        ]
    )
    decode_code(CODE, "Beginner")
    export(span_exporter)
    recorded = dict(scores)
    assert recorded["exact_resolution_ratio"] == 1.0
    assert recorded["citation_coverage"] == 1.0
    assert recorded["cited_source_count"] == 1
    assert recorded["check_format_passed"] is True
    assert "citation_issue" not in recorded


def test_ratio_scores_are_skipped_when_denominator_is_zero(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "unsupported"})
    decode_code(CODE, "Beginner")
    export(span_exporter)
    recorded = dict(scores)
    assert "exact_resolution_ratio" not in recorded  # unsupported is not a quality failure
    assert "citation_coverage" not in recorded
    assert recorded["cited_source_count"] == 0


def test_check_format_guardrail_blocks_multi_question(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "unsupported"})
    fake_openai.final_text = decode_result_json(check="질문 하나? 그리고 둘?")
    with pytest.raises(DecodeQualityError):
        decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    assert root_metadata(root_of(spans))["outcome"] == "citation_integrity_failed"
    recorded = dict(scores)
    assert recorded["check_format_passed"] is False
    assert recorded["citation_integrity_passed"] is False
    assert recorded["citation_issue"] == "invalid_check_format"


def test_page_only_lowers_exact_resolution(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "page_only"})
    decode_code(CODE, "Beginner")
    export(span_exporter)
    assert dict(scores)["exact_resolution_ratio"] == 0.0


def test_grounding_failure_records_representative_issue(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores
):
    stub_docs({"json": "exact_match"})
    fake_openai.final_text = decode_result_json(
        source=[{"source_id": "source-made-up", "title": "t", "url": "https://example.com"}]
    )
    with pytest.raises(DecodeQualityError):
        decode_code(CODE, "Beginner")
    export(span_exporter)
    recorded = dict(scores)
    assert recorded["citation_issue"] == "unverified_source"
    assert recorded["citation_coverage"] == 0.0


@pytest.mark.parametrize(("temperature", "sent"), [(0.3, 0.3), (None, None)])
def test_prompt_temperature_reaches_the_model_request(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, monkeypatch, temperature, sent
):
    from agent.prompts import LOCAL_PROMPT_CONFIG
    from tests.conftest import make_text_prompt

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    prompt_fetch["result"] = make_text_prompt(
        config={**LOCAL_PROMPT_CONFIG, "temperature": temperature}
    )
    decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    assert [body.get("temperature") for body in fake_openai.bodies] == [sent, sent]
    metadata = root_metadata(root_of(spans))
    assert metadata["modelSource"] == "prompt_config"
    assert metadata.get("temperature") == sent


def test_missing_parameters_are_not_sent(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, monkeypatch
):
    from agent.prompts import LOCAL_PROMPT_CONFIG
    from tests.conftest import make_text_prompt

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    legacy = {
        k: v for k, v in LOCAL_PROMPT_CONFIG.items() if k not in ("temperature", "reasoningEffort")
    }
    prompt_fetch["result"] = make_text_prompt(config=legacy)
    decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    for body in fake_openai.bodies:
        assert body.get("temperature") is None and not body.get("reasoning")
    metadata = root_metadata(root_of(spans))
    assert "temperature" not in metadata and "reasoningEffort" not in metadata


def test_reasoning_effort_reaches_the_model_request(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, monkeypatch
):
    from agent.prompts import LOCAL_PROMPT_CONFIG
    from tests.conftest import make_text_prompt

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    prompt_fetch["result"] = make_text_prompt(
        config={**LOCAL_PROMPT_CONFIG, "reasoningEffort": "low"}
    )
    decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    assert [body.get("reasoning", {}).get("effort") for body in fake_openai.bodies] == [
        "low",
        "low",
    ]
    assert all(body.get("temperature") is None for body in fake_openai.bodies)
    assert root_metadata(root_of(spans))["reasoningEffort"] == "low"


def test_env_model_override_sends_no_prompt_parameters(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, monkeypatch
):
    from agent.prompts import LOCAL_PROMPT_CONFIG
    from tests.conftest import make_text_prompt

    monkeypatch.setenv("OPENAI_MODEL", "emergency-model")
    prompt_fetch["result"] = make_text_prompt(
        config={
            **LOCAL_PROMPT_CONFIG,
            "model": "reasoning-model",
            "reasoningEffort": "high",
            "temperature": 0.2,
        }
    )
    decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    for body in fake_openai.bodies:
        assert body["model"] == "emergency-model"
        assert body.get("temperature") is None and not body.get("reasoning")
    metadata = root_metadata(root_of(spans))
    assert (metadata["model"], metadata["modelSource"]) == ("emergency-model", "env")


@pytest.mark.parametrize("status", [400, 401, 500])
def test_api_error_text_is_not_exported(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, status
):
    """The API error body (which may echo request content) must not reach any span."""
    fake_openai.error_status = status
    with pytest.raises(APIStatusError):
        decode_code(CODE, "Beginner")
    spans = export(span_exporter)
    root = root_of(spans)
    assert root_metadata(root)["outcome"] == "runtime_error"
    assert_no_canary(spans)
    assert_no_exception_events(spans)


def test_raw_payload_passed_by_mistake_is_dropped(span_exporter, caplog):
    with (
        caplog.at_level(logging.WARNING, logger="agent.observability"),
        observability.observation(
            "build_learning_plan", input={"rawCode": f"{CANARY}_code"}
        ) as span,
    ):
        span.update(output={"primaryTargetIds": [], "rawAnswer": f"{CANARY}_answer"})
    spans = export(span_exporter)
    assert_no_canary(spans)
    assert (
        "telemetry_payload_key_dropped name=build_learning_plan field=input key=rawCode"
        in caplog.text
    )


def test_unregistered_metadata_attribute_is_masked_at_export():
    from types import SimpleNamespace

    mask = observability._build_mask(capture_content=False)
    span = SimpleNamespace(
        instrumentation_scope_name="langfuse-sdk",
        attributes={
            "langfuse.observation.metadata.outcome": '"success"',
            "langfuse.observation.metadata.rawCode": f'"{CANARY}"',
            "langfuse.trace.metadata.anything": "x",
        },
    )
    result = mask(params=SimpleNamespace(spans={"id": span}))
    assert set(result.span_patches["id"].delete_attributes) == {
        "langfuse.observation.metadata.rawCode",
        "langfuse.trace.metadata.anything",
    }


def test_propagation_failure_does_not_break_decode(
    span_exporter, prompt_fetch, fake_openai, stub_docs, scores, monkeypatch
):
    import langfuse

    class Broken:
        def __enter__(self):
            raise RuntimeError("propagation broke")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(langfuse, "propagate_attributes", lambda **_: Broken())
    execution = decode_code(CODE, "Beginner")
    assert execution.result.what
    export(span_exporter)
