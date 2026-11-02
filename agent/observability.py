"""Langfuse tracing for decode runs.

Telemetry is fail-open: a missing key, an unreachable Langfuse server, or a bug in
this module must never change a decode result. Expected application errors are
classified inside the observation and re-raised after the observation closes, so
exception messages and stack traces (which can contain submitted code or model
output) are never recorded as OTel exception events.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from agents import set_tracing_disabled

from agent.observability_fields import (
    APP_TAG,
    CONTENT_ATTRIBUTE_KEYS,
    ROOT_METADATA_KEYS,
    ROOT_OBSERVATION_NAME,
    SCORE_TYPES,
    TRACE_NAME,
    allowed_payload_keys,
    is_allowed_attribute,
)

logger = logging.getLogger(__name__)

Level = Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"]
ObservationType = Literal["span", "chain", "retriever", "evaluator", "tool", "agent"]
ExpectedErrors = Mapping[type, tuple[Level, str]]

_TRUTHY = {"1", "true", "yes"}
_CREDENTIAL_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
_EXPORT_LOGGERS = ("opentelemetry.exporter.otlp.proto.http.trace_exporter", "langfuse")


@dataclass(frozen=True)
class ObservabilitySettings:
    """Tracing settings resolved once from the environment."""

    enabled: bool
    environment: str
    release: str | None
    sample_rate: float
    capture_content: bool
    show_trace_link: bool
    prompt_label: str = "production"
    capture_forced_off: bool = False
    missing_credentials: bool = False
    invalid_sample_rate: bool = False


def load_settings(env: Mapping[str, str] = os.environ) -> ObservabilitySettings:
    """Resolve telemetry settings from environment variables."""
    requested = env.get("LANGFUSE_ENABLED", "").lower() in _TRUTHY
    has_credentials = all(env.get(key) for key in _CREDENTIAL_KEYS)
    # Fail closed: a missing environment is "unknown", never "local", so raw
    # content capture needs an explicit LANGFUSE_TRACING_ENVIRONMENT=local.
    environment = env.get("LANGFUSE_TRACING_ENVIRONMENT") or "unknown"
    capture_requested = env.get("LANGFUSE_CAPTURE_CONTENT", "").lower() in _TRUTHY
    sample_rate, invalid_sample_rate = _sample_rate(env.get("LANGFUSE_SAMPLE_RATE"))
    return ObservabilitySettings(
        enabled=requested and has_credentials,
        environment=environment,
        release=env.get("LANGFUSE_TRACING_RELEASE") or None,
        sample_rate=sample_rate,
        # Raw content may only be captured while debugging locally.
        capture_content=capture_requested and environment == "local",
        capture_forced_off=capture_requested and environment != "local",
        show_trace_link=env.get("LANGFUSE_SHOW_TRACE_LINK", "").lower() in _TRUTHY,
        prompt_label=env.get("LANGFUSE_PROMPT_LABEL") or "production",
        missing_credentials=requested and not has_credentials,
        invalid_sample_rate=invalid_sample_rate,
    )


def _sample_rate(raw: str | None) -> tuple[float, bool]:
    """Parse a 0.0-1.0 sample rate; invalid values fall back to full collection."""
    if not raw:
        return 1.0, False
    try:
        value = float(raw)
    except ValueError:
        return 1.0, True
    if not 0.0 <= value <= 1.0:
        return 1.0, True
    return value, False


def log_event(event: str, **fields: object) -> None:
    """Write a payload-free structured telemetry log line."""
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.warning("event=%s %s", event, details)


@dataclass
class _State:
    settings: ObservabilitySettings
    client: Any = None


_state: _State | None = None
_init_lock = threading.Lock()
_reported_dropped_keys: set[tuple[str, str]] = set()


def init_observability(*, span_exporter: Any = None) -> ObservabilitySettings:
    """Configure tracing once per process. Safe to call on every decode."""
    global _state
    if _state is not None:
        return _state.settings
    with _init_lock:
        if _state is not None:
            return _state.settings
        settings = load_settings()
        if settings.missing_credentials:
            log_event("telemetry_disabled", reason="missing_credentials")
        if settings.capture_forced_off:
            log_event("telemetry_capture_forced_off", environment=settings.environment)
        if settings.invalid_sample_rate:
            log_event("telemetry_invalid_sample_rate", using=settings.sample_rate)
        if not settings.enabled:
            # Without this the Agents SDK keeps its default exporter and sends
            # traces to the OpenAI platform.
            set_tracing_disabled(True)
            _state = _State(settings=settings)
            return settings
        try:
            client = _create_client(settings, span_exporter)
        except Exception as exc:
            log_event("telemetry_init_failed", error=type(exc).__name__)
            set_tracing_disabled(True)
            settings = ObservabilitySettings(**{**settings.__dict__, "enabled": False})
            _state = _State(settings=settings)
            return settings
        _state = _State(settings=settings, client=client)
        return settings


def active_settings() -> ObservabilitySettings:
    """Return the settings actually in effect after initialization.

    Unlike load_settings(), this reflects an initialization failure.
    """
    return init_observability()


def _create_client(settings: ObservabilitySettings, span_exporter: Any) -> Any:
    from langfuse import Langfuse
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

    # The manual flag overrides OPENAI_AGENTS_DISABLE_TRACING; without it a stray
    # env var would silently drop every Agent/LLM/Tool span.
    set_tracing_disabled(False)
    client = Langfuse(
        environment=settings.environment,
        release=settings.release,
        sample_rate=settings.sample_rate,
        mask_otel_spans=_build_mask(settings.capture_content),
        span_exporter=span_exporter,
    )
    # Agents SDK tracing stays on; exclusive_processor replaces the default
    # OpenAI exporter so Langfuse is the only destination.
    OpenAIAgentsInstrumentor().instrument(
        exclusive_processor=True,
        config=TraceConfig(
            hide_inputs=not settings.capture_content,
            hide_outputs=not settings.capture_content,
        ),
    )
    _install_export_failure_logging()
    return client


def _build_mask(capture_content: bool):
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    def mask_otel_spans(*, params: Any) -> Any | None:
        patches = {}
        for identifier, span in params.spans.items():
            dropped = tuple(
                key
                for key in span.attributes
                if not is_allowed_attribute(key, capture_content=capture_content)
            )
            if dropped:
                patches[identifier] = OtelSpanPatch(delete_attributes=dropped)
                _report_unexpected_keys(span.instrumentation_scope_name or "", dropped)
        return MaskOtelSpansResult(span_patches=patches) if patches else None

    return mask_otel_spans


def _report_unexpected_keys(scope: str, dropped: tuple[str, ...]) -> None:
    """Log attribute keys that are neither allowed nor known content, once each.

    Known content keys are dropped by design. An unknown key usually means an
    instrumentation upgrade added a new attribute that needs review.
    """
    for key in dropped:
        if key in CONTENT_ATTRIBUTE_KEYS or (scope, key) in _reported_dropped_keys:
            continue
        if key.startswith(("llm.input_messages.", "llm.output_messages.", "llm.tools.")):
            continue
        _reported_dropped_keys.add((scope, key))
        log_event("telemetry_attribute_dropped", scope=scope, key=key)


class _ExportFailureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        log_event("telemetry_export_failed", source=record.name)


def _install_export_failure_logging() -> None:
    handler = _ExportFailureHandler(level=logging.ERROR)
    for name in _EXPORT_LOGGERS:
        target = logging.getLogger(name)
        if not any(isinstance(h, _ExportFailureHandler) for h in target.handlers):
            target.addHandler(handler)


class Observation:
    """Fail-open wrapper around a Langfuse observation (or nothing when disabled)."""

    def __init__(self, span: Any = None, name: str = "") -> None:
        self._span = span
        self._name = name

    @property
    def trace_id(self) -> str | None:
        return getattr(self._span, "trace_id", None)

    @property
    def id(self) -> str | None:
        return getattr(self._span, "id", None)

    def update(self, **fields: Any) -> None:
        if self._span is None:
            return
        try:
            for field in ("input", "output"):
                if field in fields:
                    fields[field] = filter_payload(self._name, field, fields[field])
            if "metadata" in fields and fields["metadata"] is not None:
                fields["metadata"] = root_metadata(fields["metadata"])
            self._span.update(**fields)
        except Exception as exc:
            log_event("telemetry_update_failed", error=type(exc).__name__)

    def score(self, name: str, value: bool | float | str) -> None:
        """Record a registered score on this observation."""
        if self._span is None:
            return
        try:
            data_type, sent = _score_value(name, value)
            self._span.score(name=name, value=sent, data_type=data_type)
        except Exception as exc:
            log_event("telemetry_score_failed", name=name, error=type(exc).__name__)


def _score_value(name: str, value: bool | float | str) -> tuple[str, float | str]:
    """Convert a value to what Langfuse expects for the registered score type."""
    data_type = SCORE_TYPES.get(name)
    if data_type is None:
        raise KeyError(name)
    if data_type == "BOOLEAN":
        return data_type, 1.0 if value else 0.0
    if data_type == "NUMERIC":
        return data_type, float(value)
    return data_type, str(value)


def record_user_feedback(trace_id: str | None, observation_id: str | None, positive: bool) -> None:
    """Record 👍/👎 on a decode run. Re-clicking updates the same score."""
    if not trace_id or _state is None or _state.client is None:
        return
    try:
        data_type, value = _score_value("user_feedback", positive)
        _state.client.create_score(
            name="user_feedback",
            value=value,
            data_type=data_type,
            trace_id=trace_id,
            observation_id=observation_id,
            # Stable ID so a Streamlit rerun or a changed vote updates one score.
            score_id=f"{trace_id}-user_feedback",
        )
    except Exception as exc:
        log_event("telemetry_score_failed", name="user_feedback", error=type(exc).__name__)


def _classify(
    exc: BaseException, expected: ExpectedErrors, fallback_code: str | None
) -> tuple[Level, str]:
    for error_type, (level, code) in expected.items():
        if isinstance(exc, error_type):
            return level, code
    if fallback_code:
        return "ERROR", f"{fallback_code}:{type(exc).__name__}"
    return "ERROR", type(exc).__name__


@contextmanager
def observation(
    name: str,
    *,
    as_type: ObservationType = "span",
    input: Any = None,
    expected: ExpectedErrors | None = None,
    fallback_code: str | None = None,
) -> Iterator[Observation]:
    """Open a child observation and classify any exception that leaves it.

    The exception is caught inside the observation, recorded only as a level and
    a classification code, and re-raised after the observation has ended.
    """
    client = _state.client if _state is not None else None
    manager = None
    observed = Observation()
    if client is not None:
        try:
            manager = client.start_as_current_observation(
                name=name, as_type=as_type, input=filter_payload(name, "input", input)
            )
            observed = Observation(manager.__enter__(), name)
        except Exception as exc:
            log_event("telemetry_observation_failed", name=name, error=type(exc).__name__)
            manager = None
    error: BaseException | None = None
    try:
        yield observed
    except Exception as exc:
        error = exc
        level, code = _classify(exc, expected or {}, fallback_code)
        observed.update(level=level, status_message=code)
    finally:
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:
                log_event("telemetry_observation_failed", name=name, error=type(exc).__name__)
    if error is not None:
        raise error


@contextmanager
def decode_trace(
    *,
    session_id: str | None,
    level: str,
    input: Any,
    expected: ExpectedErrors,
) -> Iterator[Observation]:
    """Open the root observation for one decode run and propagate trace attributes."""
    init_observability()
    with (
        observation(
            ROOT_OBSERVATION_NAME,
            as_type="chain",
            input=input,
            expected=expected,
            fallback_code="runtime_error",
        ) as root,
        _propagate(session_id=session_id, tags=[APP_TAG, f"level:{level.lower()}"]),
    ):
        yield root


def _propagate(*, session_id: str | None, tags: list[str]):
    return _safe_propagation(session_id=session_id, tags=tags, trace_name=TRACE_NAME)


@contextmanager
def _safe_propagation(**attributes: Any) -> Iterator[None]:
    """Enter Langfuse attribute propagation without letting it fail the decode.

    propagate_attributes() only builds a context manager; the real work happens
    in __enter__/__exit__, so those are guarded too.
    """
    manager = None
    if _state is not None and _state.client is not None:
        try:
            from langfuse import propagate_attributes

            manager = propagate_attributes(**attributes)
            manager.__enter__()
        except Exception as exc:
            log_event("telemetry_propagation_failed", error=type(exc).__name__)
            manager = None
    try:
        yield
    finally:
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:
                log_event("telemetry_propagation_failed", error=type(exc).__name__)


def prompt_client() -> Any:
    """Return the Langfuse client for prompt fetches, or None when disabled."""
    return _state.client if _state is not None else None


def prompt_label() -> str:
    """Return the Langfuse prompt label to fetch."""
    return _state.settings.prompt_label if _state is not None else "production"


def linked_prompt(remote_prompt: Any, *, level: str, prompt_source: str):
    """Link generations created in this context to a Langfuse prompt version.

    Fallback prompts are not Langfuse versions, so they are never linked.
    """
    tags = [APP_TAG, f"level:{level.lower()}", f"prompt_source:{prompt_source}"]
    if remote_prompt is None:
        return _safe_propagation(tags=tags)
    return _safe_propagation(prompt=remote_prompt, tags=tags)


def filter_payload(name: str, field: str, value: Any) -> Any:
    """Keep only the input/output keys registered for this observation."""
    if value is None:
        return None
    allowed = allowed_payload_keys(name, field, capture_content=capture_content())
    if not isinstance(value, Mapping):
        log_event("telemetry_payload_dropped", name=name, field=field)
        return None
    kept = {}
    for key, item in value.items():
        if key in allowed:
            kept[key] = item
        else:
            log_event("telemetry_payload_key_dropped", name=name, field=field, key=key)
    return kept


def root_metadata(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return only registered root metadata keys, logging any unregistered key."""
    accepted = {}
    for key, value in values.items():
        if key not in ROOT_METADATA_KEYS:
            log_event("telemetry_unknown_metadata_key", key=key)
            continue
        accepted[key] = value
    return accepted


def capture_content() -> bool:
    """Return whether raw model inputs and outputs may be traced."""
    return _state is not None and _state.settings.capture_content


def trace_url(trace_id: str | None) -> str | None:
    """Return a project-scoped Langfuse trace URL when link display is enabled."""
    if not trace_id or _state is None or _state.client is None:
        return None
    if not _state.settings.show_trace_link:
        return None
    try:
        return _state.client.get_trace_url(trace_id=trace_id)
    except Exception as exc:
        log_event("telemetry_trace_url_failed", error=type(exc).__name__)
        return None


def flush() -> None:
    """Send buffered spans to Langfuse."""
    if _state is not None and _state.client is not None:
        try:
            _state.client.flush()
        except Exception as exc:
            log_event("telemetry_flush_failed", error=type(exc).__name__)
