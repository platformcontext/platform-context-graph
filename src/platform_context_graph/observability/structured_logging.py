"""Shared structured logging bootstrap and formatters."""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import IO, Any

from .otel import (
    current_component,
    current_correlation_id,
    current_request_id,
    current_transport,
    package_version,
    resource_attributes,
    service_name_for_component,
)

try:
    from opentelemetry import trace
except ImportError:  # pragma: no cover - optional dependency
    trace = None  # type: ignore[assignment]

_LOGGING_STATE_LOCK = Lock()
_STANDARD_LOG_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys())
_RESERVED_KEYS = frozenset(
    {
        "timestamp",
        "severity_text",
        "severity_number",
        "message",
        "event_name",
        "logger_name",
        "service_name",
        "service_namespace",
        "service_version",
        "deployment_environment",
        "component",
        "transport",
        "runtime_role",
        "trace_id",
        "span_id",
        "request_id",
        "correlation_id",
        "exception_type",
        "exception_message",
        "exception_stacktrace",
        "extra_keys",
    }
)
_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "DISABLED": logging.CRITICAL + 10,
}


@dataclass(slots=True)
class _LoggingState:
    """Runtime logging metadata shared by all emitted records."""

    component: str
    runtime_role: str
    service_name: str
    resource: dict[str, str]
    stream: IO[str] | None = None


_LOGGING_STATE = _LoggingState(
    component="unknown",
    runtime_role="unknown",
    service_name="platform-context-graph-api",
    resource=resource_attributes("platform-context-graph-api"),
    stream=None,
)


def _get_config_value(key: str, default: str | None = None) -> str | None:
    """Read one config value with safe fallbacks before config bootstrap."""

    value = os.getenv(key)
    if value is not None:
        return value
    try:
        from platform_context_graph.cli.config_manager import get_config_value

        resolved = get_config_value(key)
        if resolved is not None:
            return str(resolved)
    except Exception:
        return default
    return default


def logging_level_from_config() -> int:
    """Return the configured application log level as a numeric value."""

    configured = str(_get_config_value("ENABLE_APP_LOGS", "INFO") or "INFO").upper()
    return _LOG_LEVELS.get(configured, logging.INFO)


def logging_format_from_config() -> str:
    """Return the configured log format."""

    configured = str(_get_config_value("PCG_LOG_FORMAT", "json") or "json").lower()
    if configured not in {"json", "text"}:
        return "json"
    return configured


def library_log_level_from_config() -> int:
    """Return the configured third-party logger threshold."""

    configured = str(_get_config_value("LIBRARY_LOG_LEVEL", "WARNING") or "WARNING")
    return getattr(logging, configured.upper(), logging.WARNING)


def debug_file_logging_enabled() -> bool:
    """Return whether the legacy debug file sink is enabled."""

    configured = str(_get_config_value("DEBUG_LOGS", "false") or "false").lower()
    return configured in {"1", "true", "yes", "on"}


def debug_log_path() -> Path:
    """Return the configured legacy debug log file path."""

    configured = _get_config_value(
        "DEBUG_LOG_PATH", os.path.expanduser("~/mcp_debug.log")
    )
    return Path(str(configured))


def app_log_path() -> Path:
    """Return the configured legacy app log file path."""

    configured = _get_config_value("LOG_FILE_PATH")
    if configured is None or not str(configured).strip():
        return Path(os.devnull)
    return Path(str(configured))


def _severity_number(levelno: int) -> int:
    """Map stdlib levels to OpenTelemetry-compatible severity numbers."""

    if levelno >= logging.CRITICAL:
        return 21
    if levelno >= logging.ERROR:
        return 17
    if levelno >= logging.WARNING:
        return 13
    if levelno >= logging.INFO:
        return 9
    return 5


def _stringify_json_value(value: Any) -> Any:
    """Return a JSON-friendly representation for arbitrary Python values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _stringify_json_value(item)
            for key, item in value.items()
            if str(key) not in _RESERVED_KEYS
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_stringify_json_value(item) for item in value]
    return str(value)


def _active_span_ids() -> tuple[str | None, str | None]:
    """Return the active trace/span identifiers when tracing is enabled."""

    if trace is None:
        return None, None
    current_span = trace.get_current_span()
    if current_span is None:
        return None, None
    span_context = current_span.get_span_context()
    if span_context is None or not span_context.is_valid:
        return None, None
    return f"{span_context.trace_id:032x}", f"{span_context.span_id:016x}"


def _extra_keys_from_record(record: logging.LogRecord) -> dict[str, Any]:
    """Collect user-supplied extras while protecting the reserved schema."""

    extra_keys: dict[str, Any] = {}
    raw_extra_keys = getattr(record, "extra_keys", None)
    if isinstance(raw_extra_keys, dict):
        extra_keys.update(
            {
                str(key): _stringify_json_value(value)
                for key, value in raw_extra_keys.items()
                if str(key) not in _RESERVED_KEYS
            }
        )

    for key, value in record.__dict__.items():
        if (
            key in _STANDARD_LOG_RECORD_KEYS
            or key in {"event_name", "extra_keys"}
            or key in _RESERVED_KEYS
            or key.startswith("_")
        ):
            continue
        extra_keys[key] = _stringify_json_value(value)
    return extra_keys


class StructuredJsonFormatter(logging.Formatter):
    """Emit one canonical JSON document per log record."""

    def format(self, record: logging.LogRecord) -> str:
        """Format one log record using the shared schema."""

        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(
            timespec="milliseconds"
        )
        trace_id, span_id = _active_span_ids()
        with _LOGGING_STATE_LOCK:
            state = _LOGGING_STATE

        component = current_component() or state.component
        transport = current_transport()
        request_id = current_request_id()
        correlation_id = current_correlation_id()
        exception_type: str | None = None
        exception_message: str | None = None
        exception_stacktrace: str | None = None
        if record.exc_info:
            exc_type = record.exc_info[0]
            exc_value = record.exc_info[1]
            exception_type = exc_type.__name__ if exc_type is not None else None
            exception_message = str(exc_value) if exc_value is not None else None
            exception_stacktrace = "".join(traceback.format_exception(*record.exc_info))

        payload = {
            "timestamp": timestamp.replace("+00:00", "Z"),
            "severity_text": record.levelname,
            "severity_number": _severity_number(record.levelno),
            "message": record.getMessage(),
            "event_name": getattr(record, "event_name", None),
            "logger_name": record.name,
            "service_name": state.resource.get("service.name", state.service_name),
            "service_namespace": state.resource.get("service.namespace"),
            "service_version": state.resource.get("service.version", package_version()),
            "deployment_environment": state.resource.get("deployment.environment"),
            "component": component,
            "transport": transport,
            "runtime_role": state.runtime_role,
            "trace_id": trace_id,
            "span_id": span_id,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "exception_type": exception_type,
            "exception_message": exception_message,
            "exception_stacktrace": exception_stacktrace,
            "extra_keys": _extra_keys_from_record(record),
        }
        return json.dumps(payload, ensure_ascii=True, default=str)


class StructuredTextFormatter(logging.Formatter):
    """Human-readable fallback formatter for explicit local overrides."""

    def format(self, record: logging.LogRecord) -> str:
        """Render a concise text line with the shared context fields."""

        trace_id, span_id = _active_span_ids()
        with _LOGGING_STATE_LOCK:
            state = _LOGGING_STATE
        component = current_component() or state.component
        request_id = current_request_id()
        event_name = getattr(record, "event_name", None)
        extras = _extra_keys_from_record(record)
        extras_text = ""
        if extras:
            extras_text = (
                f" extra_keys={json.dumps(extras, ensure_ascii=True, default=str)}"
            )
        return (
            f"{datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')} "
            f"{record.levelname} {record.name} component={component} "
            f"runtime_role={state.runtime_role} request_id={request_id or '-'} "
            f"trace_id={trace_id or '-'} span_id={span_id or '-'} "
            f"event_name={event_name or '-'} message={record.getMessage()}{extras_text}"
        )


def _handler_with_formatter(
    *,
    stream: IO[str] | None = None,
    path: Path | None = None,
) -> logging.Handler:
    """Build one handler using the configured formatter."""

    handler: logging.Handler
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    else:
        handler = logging.StreamHandler(stream or sys.stdout)

    if logging_format_from_config() == "text":
        handler.setFormatter(StructuredTextFormatter())
    else:
        handler.setFormatter(StructuredJsonFormatter())
    return handler


def _optional_file_handler_with_formatter(
    path: Path,
) -> tuple[logging.Handler | None, dict[str, str] | None]:
    """Build an optional file handler, returning warning metadata on failure."""

    try:
        return _handler_with_formatter(path=path), None
    except OSError as exc:
        return None, {
            "error": str(exc),
            "path": str(path),
        }


def _configure_library_loggers() -> None:
    """Apply the configured third-party logger threshold."""

    log_level = library_log_level_from_config()
    logging.getLogger("neo4j").setLevel(log_level)
    logging.getLogger("asyncio").setLevel(log_level)
    logging.getLogger("urllib3").setLevel(log_level)


def configure_logging(
    *,
    component: str,
    runtime_role: str | None = None,
    stream: IO[str] | None = None,
) -> None:
    """Configure process-wide logging for structured stdout output."""

    service_name = service_name_for_component(component)
    resource = resource_attributes(service_name)
    with _LOGGING_STATE_LOCK:
        global _LOGGING_STATE
        previous_stream = _LOGGING_STATE.stream
        _LOGGING_STATE = _LoggingState(
            component=component,
            runtime_role=runtime_role or component,
            service_name=service_name,
            resource=resource,
            stream=stream or previous_stream,
        )

    handlers: list[logging.Handler] = [
        _handler_with_formatter(stream=_LOGGING_STATE.stream)
    ]
    deferred_sink_warnings: list[dict[str, str]] = []
    legacy_log_path = app_log_path()
    if legacy_log_path != Path(os.devnull):
        legacy_handler, warning = _optional_file_handler_with_formatter(legacy_log_path)
        if legacy_handler is not None:
            handlers.append(legacy_handler)
        elif warning is not None:
            warning["sink"] = "app"
            deferred_sink_warnings.append(warning)
    logging.basicConfig(
        level=logging_level_from_config(),
        handlers=handlers,
        force=True,
    )
    debug_logger = logging.getLogger("platform_context_graph.debug")
    debug_logger.handlers.clear()
    debug_logger.propagate = False
    debug_logger.setLevel(logging.DEBUG)
    if debug_file_logging_enabled():
        debug_handler, warning = _optional_file_handler_with_formatter(debug_log_path())
        if debug_handler is not None:
            debug_logger.addHandler(debug_handler)
        elif warning is not None:
            warning["sink"] = "debug"
            deferred_sink_warnings.append(warning)
    _configure_library_loggers()
    if deferred_sink_warnings:
        logger = logging.getLogger(__name__)
        for warning in deferred_sink_warnings:
            emit_structured_log(
                logger,
                logging.WARNING,
                "Optional legacy log file sink unavailable; continuing with stdout logging",
                event_name="logging.file_sink.unavailable",
                extra_keys=warning,
            )


def emit_structured_log(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> None:
    """Emit one structured log record through the shared logging pipeline."""

    logger.log(
        level,
        message,
        exc_info=exc_info,
        extra={
            "event_name": event_name,
            "extra_keys": dict(extra_keys or {}),
        },
    )


__all__ = [
    "StructuredJsonFormatter",
    "configure_logging",
    "debug_file_logging_enabled",
    "debug_log_path",
    "emit_structured_log",
    "logging_format_from_config",
    "logging_level_from_config",
]
