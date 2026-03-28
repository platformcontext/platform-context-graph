from __future__ import annotations

import importlib
import io
import json
import logging
from pathlib import Path

import pytest

pytest.importorskip("opentelemetry.sdk")
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _parse_log_lines(buffer: io.StringIO) -> list[dict[str, object]]:
    """Return parsed JSON log records from an in-memory log stream."""

    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_configure_logging_emits_json_schema_and_sanitizes_extra_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured logs must emit the shared schema and protect reserved fields."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    buffer = io.StringIO()
    monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")
    monkeypatch.setenv("PCG_DEPLOYMENT_ENVIRONMENT", "test")

    observability.configure_logging(
        component="api",
        runtime_role="api",
        stream=buffer,
    )

    logger = logging.getLogger("tests.structured")
    logger.info(
        "structured message",
        extra={
            "event_name": "test.structured",
            "extra_keys": {
                "repo_id": "repository:r_123",
                "service_name": "bad-override",
                "trace_id": "bad-trace",
            },
        },
    )

    records = _parse_log_lines(buffer)
    assert len(records) == 1
    record = records[0]
    assert record["message"] == "structured message"
    assert record["event_name"] == "test.structured"
    assert record["logger_name"] == "tests.structured"
    assert record["severity_text"] == "INFO"
    assert record["severity_number"] == 9
    assert record["service_name"] == "platform-context-graph-api"
    assert record["service_namespace"] == "platformcontext"
    assert record["deployment_environment"] == "test"
    assert record["component"] == "api"
    assert record["runtime_role"] == "api"
    assert record["extra_keys"] == {"repo_id": "repository:r_123"}
    assert record["request_id"] is None
    assert record["correlation_id"] is None
    assert record["trace_id"] is None
    assert record["span_id"] is None


def test_configure_logging_includes_exception_fields_and_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured logs should carry request/span correlation and exception data."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )
    monkeypatch.setenv("ENABLE_APP_LOGS", "ERROR")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")

    runtime = observability.initialize_observability(
        component="api",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )
    buffer = io.StringIO()
    observability.configure_logging(
        component="api",
        runtime_role="api",
        stream=buffer,
    )

    logger = logging.getLogger("tests.exceptions")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        with runtime.request_context(
            component="api",
            transport="http",
            request_id="req-123",
            correlation_id="corr-456",
        ):
            with runtime.start_span("pcg.test.logging"):
                logger.error(
                    "failed request",
                    exc_info=True,
                    extra={
                        "event_name": "test.exception",
                        "extra_keys": {"repo_path": "/tmp/repo"},
                    },
                )

    records = _parse_log_lines(buffer)
    assert len(records) == 1
    record = records[0]
    assert record["event_name"] == "test.exception"
    assert record["component"] == "api"
    assert record["transport"] == "http"
    assert record["request_id"] == "req-123"
    assert record["correlation_id"] == "corr-456"
    assert isinstance(record["trace_id"], str) and record["trace_id"]
    assert isinstance(record["span_id"], str) and record["span_id"]
    assert record["exception_type"] == "RuntimeError"
    assert record["exception_message"] == "boom"
    assert "RuntimeError: boom" in str(record["exception_stacktrace"])
    assert record["extra_keys"] == {"repo_path": "/tmp/repo"}


def test_request_context_without_ids_serializes_null_request_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitted request and correlation IDs must stay null in emitted JSON logs."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    buffer = io.StringIO()
    monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")

    runtime = observability.initialize_observability(component="bootstrap-index")
    observability.configure_logging(
        component="bootstrap-index",
        runtime_role="bootstrap-index",
        stream=buffer,
    )

    logger = logging.getLogger("tests.request_context")
    with runtime.request_context(component="bootstrap-index"):
        logger.warning("background operation")

    records = _parse_log_lines(buffer)
    assert len(records) == 1
    record = records[0]
    assert record["request_id"] is None
    assert record["correlation_id"] is None


def test_emit_log_call_falls_back_for_message_only_logger() -> None:
    """Legacy message-only loggers should still be callable through the shim."""

    debug_log = importlib.import_module("platform_context_graph.utils.debug_log")
    captured: list[str] = []

    def legacy_logger(message: str) -> None:
        captured.append(message)

    debug_log.emit_log_call(
        legacy_logger,
        "legacy message",
        event_name="test.legacy",
        extra_keys={"repo_id": "repository:r_123"},
    )

    assert captured == ["legacy message"]


def test_emit_log_call_reraises_internal_type_errors() -> None:
    """The compatibility shim must not swallow real logger implementation bugs."""

    debug_log = importlib.import_module("platform_context_graph.utils.debug_log")

    def broken_logger(
        message: str,
        *,
        event_name: str | None = None,
        extra_keys: dict[str, object] | None = None,
        exc_info: object = None,
    ) -> None:
        del message, event_name, extra_keys, exc_info
        raise TypeError("boom")

    with pytest.raises(TypeError, match="boom"):
        debug_log.emit_log_call(
            broken_logger,
            "broken message",
            event_name="test.broken",
        )


def test_configure_logging_continues_when_legacy_log_file_is_unwritable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unwritable legacy app log path must degrade to stdout-only logging."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    buffer = io.StringIO()
    monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_FILE_PATH", "/tmp/blocked/pcg.log")

    file_handler = logging.FileHandler

    def blocked_file_handler(path: str | Path, *args: object, **kwargs: object) -> logging.Handler:
        if Path(path) == Path("/tmp/blocked/pcg.log"):
            raise PermissionError("permission denied")
        return file_handler(path, *args, **kwargs)

    monkeypatch.setattr(logging, "FileHandler", blocked_file_handler)

    observability.configure_logging(component="cli", runtime_role="cli", stream=buffer)

    records = _parse_log_lines(buffer)
    assert len(records) == 1
    record = records[0]
    assert record["severity_text"] == "WARNING"
    assert record["event_name"] == "logging.file_sink.unavailable"
    assert record["message"] == "Optional legacy log file sink unavailable; continuing with stdout logging"
    assert record["extra_keys"] == {
        "error": "permission denied",
        "path": "/tmp/blocked/pcg.log",
        "sink": "app",
    }


def test_configure_logging_continues_when_debug_log_file_is_unwritable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unwritable debug log path must not crash logging bootstrap."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    buffer = io.StringIO()
    monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_FILE_PATH", "")
    monkeypatch.setenv("DEBUG_LOGS", "true")
    monkeypatch.setenv("DEBUG_LOG_PATH", "/tmp/blocked/mcp_debug.log")

    file_handler = logging.FileHandler

    def blocked_file_handler(path: str | Path, *args: object, **kwargs: object) -> logging.Handler:
        if Path(path) == Path("/tmp/blocked/mcp_debug.log"):
            raise PermissionError("permission denied")
        return file_handler(path, *args, **kwargs)

    monkeypatch.setattr(logging, "FileHandler", blocked_file_handler)

    observability.configure_logging(component="cli", runtime_role="cli", stream=buffer)

    records = _parse_log_lines(buffer)
    assert len(records) == 1
    record = records[0]
    assert record["severity_text"] == "WARNING"
    assert record["event_name"] == "logging.file_sink.unavailable"
    assert record["message"] == "Optional legacy log file sink unavailable; continuing with stdout logging"
    assert record["extra_keys"] == {
        "error": "permission denied",
        "path": "/tmp/blocked/mcp_debug.log",
        "sink": "debug",
    }
