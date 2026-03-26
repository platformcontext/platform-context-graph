"""Compatibility logging helpers backed by the shared structured logger."""

from __future__ import annotations

import inspect
import logging
from typing import Any

from platform_context_graph.observability.structured_logging import (
    debug_file_logging_enabled,
    emit_structured_log,
    logging_level_from_config,
)

logger = logging.getLogger(__name__)
debug_file_logger = logging.getLogger("platform_context_graph.debug")

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "DISABLED": logging.CRITICAL + 10,
}


def _should_log(level_name: str) -> bool:
    """Return whether a message at the given level should be emitted."""

    configured_level = logging_level_from_config()
    if configured_level > logging.CRITICAL:
        return False
    return LOG_LEVELS.get(level_name.upper(), logging.INFO) >= configured_level


def emit_log_call(
    logger_fn: Any,
    message: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> Any:
    """Call a logger-compatible function with structured kwargs when supported."""

    if not callable(logger_fn):
        return None
    signature_supports_kwargs = _supports_structured_kwargs(logger_fn)
    if signature_supports_kwargs is False:
        return logger_fn(message)
    try:
        return logger_fn(
            message,
            event_name=event_name,
            extra_keys=extra_keys,
            exc_info=exc_info,
        )
    except TypeError as exc:
        if not _looks_like_unsupported_kwargs(exc):
            raise
        return logger_fn(message)


def _supports_structured_kwargs(logger_fn: Any) -> bool | None:
    """Return whether a callable advertises support for structured log kwargs."""

    try:
        signature = inspect.signature(logger_fn)
    except (TypeError, ValueError):
        return None

    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return True

    supported = {
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return {"event_name", "extra_keys", "exc_info"}.issubset(supported)


def _looks_like_unsupported_kwargs(exc: TypeError) -> bool:
    """Return whether a ``TypeError`` came from incompatible call kwargs."""

    message = str(exc)
    return (
        "unexpected keyword argument" in message
        or "positional argument but" in message
        or "positional arguments but" in message
    )


def debug_log(
    message: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> None:
    """Emit a legacy debug-file log through the structured logging pipeline."""

    if not debug_file_logging_enabled():
        return
    emit_structured_log(
        debug_file_logger,
        logging.DEBUG,
        message,
        event_name=event_name,
        extra_keys=extra_keys,
        exc_info=exc_info,
    )


def info_logger(
    msg: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> None:
    """Log an info message when the configured threshold allows it."""

    if _should_log("INFO"):
        emit_structured_log(
            logger,
            logging.INFO,
            msg,
            event_name=event_name,
            extra_keys=extra_keys,
            exc_info=exc_info,
        )


def error_logger(
    msg: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> None:
    """Log an error message when the configured threshold allows it."""

    if _should_log("ERROR"):
        emit_structured_log(
            logger,
            logging.ERROR,
            msg,
            event_name=event_name,
            extra_keys=extra_keys,
            exc_info=exc_info,
        )


def warning_logger(
    msg: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> None:
    """Log a warning message when the configured threshold allows it."""

    if _should_log("WARNING"):
        emit_structured_log(
            logger,
            logging.WARNING,
            msg,
            event_name=event_name,
            extra_keys=extra_keys,
            exc_info=exc_info,
        )


def debug_logger(
    msg: str,
    *,
    event_name: str | None = None,
    extra_keys: dict[str, Any] | None = None,
    exc_info: Any = None,
) -> None:
    """Log a debug message when the configured threshold allows it."""

    if _should_log("DEBUG"):
        emit_structured_log(
            logger,
            logging.DEBUG,
            msg,
            event_name=event_name,
            extra_keys=extra_keys,
            exc_info=exc_info,
        )
