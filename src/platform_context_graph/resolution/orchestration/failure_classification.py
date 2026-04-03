"""Failure classification helpers for the Resolution Engine."""

from __future__ import annotations

from platform_context_graph.facts.work_queue.failure_types import (
    FailureClassification,
)
from platform_context_graph.facts.work_queue.failure_types import FailureClass
from platform_context_graph.facts.work_queue.failure_types import FailureDisposition


def _failure_code(exc: BaseException) -> str:
    """Return a stable snake_case failure code for one exception."""

    return (
        exc.__class__.__name__.replace("Error", "_error")
        .replace("Exception", "_exception")
        .replace("__", "_")
        .lower()
    )


def classify_resolution_failure(
    exc: BaseException,
    *,
    failure_stage: str,
) -> FailureClassification:
    """Map one projection exception into durable failure metadata."""

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
