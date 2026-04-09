"""Failure classification helpers for the Resolution Engine."""

from __future__ import annotations

import re

from platform_context_graph.facts.work_queue.failure_types import (
    FailureClassification,
)
from platform_context_graph.facts.work_queue.failure_types import FailureClass
from platform_context_graph.facts.work_queue.failure_types import FailureDisposition

_NEO4J_TRANSIENT_CODE_PREFIX = "Neo.TransientError."
_NEO4J_TRANSIENT_RETRY_SECONDS = 15


def _failure_code(exc: BaseException) -> str:
    """Return a stable snake_case failure code for one exception."""

    return (
        exc.__class__.__name__.replace("Error", "_error")
        .replace("Exception", "_exception")
        .replace("__", "_")
        .lower()
    )


def _neo4j_error_code(exc: BaseException) -> str | None:
    """Return the Neo4j server error code when one is available."""

    for attribute in ("code", "_neo4j_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _neo4j_failure_code(exc: BaseException) -> str:
    """Return a normalized failure code derived from a Neo4j server code."""

    raw_code = _neo4j_error_code(exc)
    if raw_code is None:
        return _failure_code(exc)
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw_code.replace(".", "_"))
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.lower()


def _is_retryable_neo4j_transient(exc: BaseException) -> bool:
    """Return whether the exception is a retryable Neo4j transient error."""

    code = _neo4j_error_code(exc)
    return bool(code and code.startswith(_NEO4J_TRANSIENT_CODE_PREFIX))


def classify_resolution_failure(
    exc: BaseException,
    *,
    failure_stage: str,
) -> FailureClassification:
    """Map one projection exception into durable failure metadata."""

    if _is_retryable_neo4j_transient(exc):
        return FailureClassification(
            failure_stage=failure_stage,
            error_class=type(exc).__name__,
            failure_class=FailureClass.DEPENDENCY_UNAVAILABLE,
            failure_code=_neo4j_failure_code(exc),
            retry_disposition=FailureDisposition.RETRYABLE,
            retry_after_seconds=_NEO4J_TRANSIENT_RETRY_SECONDS,
        )
    if isinstance(exc, TimeoutError):
        return FailureClassification(
            failure_stage=failure_stage,
            error_class=type(exc).__name__,
            failure_class=FailureClass.TIMEOUT,
            failure_code=_failure_code(exc),
            retry_disposition=FailureDisposition.RETRYABLE,
        )
    if isinstance(exc, (ValueError, TypeError)):
        return FailureClassification(
            failure_stage=failure_stage,
            error_class=type(exc).__name__,
            failure_class=FailureClass.INPUT_INVALID,
            failure_code=_failure_code(exc),
            retry_disposition=FailureDisposition.NON_RETRYABLE,
        )
    if isinstance(exc, (ConnectionError, OSError)):
        return FailureClassification(
            failure_stage=failure_stage,
            error_class=type(exc).__name__,
            failure_class=FailureClass.DEPENDENCY_UNAVAILABLE,
            failure_code=_failure_code(exc),
            retry_disposition=FailureDisposition.RETRYABLE,
        )
    if isinstance(exc, MemoryError):
        return FailureClassification(
            failure_stage=failure_stage,
            error_class=type(exc).__name__,
            failure_class=FailureClass.RESOURCE_EXHAUSTED,
            failure_code=_failure_code(exc),
            retry_disposition=FailureDisposition.MANUAL_REVIEW,
        )
    return FailureClassification(
        failure_stage=failure_stage,
        error_class=type(exc).__name__,
        failure_class=FailureClass.PROJECTION_BUG,
        failure_code=_failure_code(exc),
        retry_disposition=FailureDisposition.MANUAL_REVIEW,
    )
