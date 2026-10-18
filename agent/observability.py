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
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Literal, Optional

from agents import set_tracing_disabled

from agent.observability_fields import (
    APP_TAG,
    CONTENT_ATTRIBUTE_KEYS,
    ROOT_METADATA_KEYS,
    ROOT_OBSERVATION_NAME,
    SCORE_NAMES,
    TRACE_NAME,
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
    enabled: bool
    environment: str
    release: Optional[str]
    sample_rate: float
    capture_content: bool
    show_trace_link: bool
    capture_forced_off: bool = False
    missing_credentials: bool = False


def load_settings(env: Mapping[str, str] = os.environ) -> ObservabilitySettings:
    """Resolve telemetry settings from environment variables."""
    requested = env.get("LANGFUSE_ENABLED", "").lower() in _TRUTHY
    has_credentials = all(env.get(key) for key in _CREDENTIAL_KEYS)
    environment = env.get("LANGFUSE_TRACING_ENVIRONMENT") or "local"
    capture_requested = env.get("LANGFUSE_CAPTURE_CONTENT", "").lower() in _TRUTHY
    try:
        sample_rate = float(env.get("LANGFUSE_SAMPLE_RATE") or 1.0)
    except ValueError:
        sample_rate = 1.0
    return ObservabilitySettings(
        enabled=requested and has_credentials,
        environment=environment,
        release=env.get("LANGFUSE_TRACING_RELEASE") or None,
        sample_rate=sample_rate,
        # Raw content may only be captured while debugging locally.
        capture_content=capture_requested and environment == "local",
        capture_forced_off=capture_requested and environment != "local",
        show_trace_link=env.get("LANGFUSE_SHOW_TRACE_LINK", "").lower() in _TRUTHY,
        missing_credentials=requested and not has_credentials,
    )


def log_event(event: str, **fields: object) -> None:
    """Write a payload-free structured telemetry log line."""
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.warning("event=%s %s", event, details)


@dataclass
class _State:
    settings: ObservabilitySettings
    client: Any = None


_state: Optional[_State] = None
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


def _create_client(settings: ObservabilitySettings, span_exporter: Any) -> Any:
    from langfuse import Langfuse
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

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

    def mask_otel_spans(*, params: Any) -> Optional[Any]:
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

    def __init__(self, span: Any = None) -> None:
        self._span = span

    @property
    def trace_id(self) -> Optional[str]:
        return getattr(self._span, "trace_id", None)

    @property
    def id(self) -> Optional[str]:
        return getattr(self._span, "id", None)

    def update(self, **fields: Any) -> None:
        if self._span is None:
            return
        try:
            self._span.update(**fields)
        except Exception as exc:
            log_event("telemetry_update_failed", error=type(exc).__name__)

    def score(self, name: str, passed: bool) -> None:
        """Record a boolean score on this observation."""
        if self._span is None:
            return
        if name not in SCORE_NAMES:
            log_event("telemetry_unknown_score", name=name)
            return
        try:
            self._span.score(name=name, value=1.0 if passed else 0.0, data_type="BOOLEAN")
        except Exception as exc:
            log_event("telemetry_score_failed", name=name, error=type(exc).__name__)


def _classify(
    exc: BaseException, expected: ExpectedErrors, fallback_code: Optional[str]
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
    fallback_code: Optional[str] = None,
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
            manager = client.start_as_current_observation(name=name, as_type=as_type, input=input)
            observed = Observation(manager.__enter__())
        except Exception as exc:
            log_event("telemetry_observation_failed", name=name, error=type(exc).__name__)
            manager = None
    error: Optional[BaseException] = None
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
    session_id: Optional[str],
    level: str,
    input: Any,
    expected: ExpectedErrors,
) -> Iterator[Observation]:
    """Open the root observation for one decode run and propagate trace attributes."""
    init_observability()
    with observation(
        ROOT_OBSERVATION_NAME,
        as_type="chain",
        input=input,
        expected=expected,
        fallback_code="runtime_error",
    ) as root:
        with _propagate(session_id=session_id, tags=[APP_TAG, f"level:{level.lower()}"]):
            yield root


def _propagate(*, session_id: Optional[str], tags: list[str]):
    if _state is None or _state.client is None:
        return nullcontext()
    try:
        from langfuse import propagate_attributes

        return propagate_attributes(session_id=session_id, tags=tags, trace_name=TRACE_NAME)
    except Exception as exc:
        log_event("telemetry_propagation_failed", error=type(exc).__name__)
        return nullcontext()


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
    return _state is not None and _state.settings.capture_content


def trace_url(trace_id: Optional[str]) -> Optional[str]:
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
    if _state is not None and _state.client is not None:
        try:
            _state.client.flush()
        except Exception as exc:
            log_event("telemetry_flush_failed", error=type(exc).__name__)
