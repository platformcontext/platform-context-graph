"""Tests for resolution failure classification."""

from __future__ import annotations

from platform_context_graph.facts.work_queue.failure_types import FailureClass
from platform_context_graph.facts.work_queue.failure_types import FailureDisposition
from platform_context_graph.resolution.orchestration.failure_classification import (
    classify_resolution_failure,
)


def test_classify_timeout_error_as_retryable_timeout() -> None:
    """Timeouts should classify as retryable timeout failures."""

    classification = classify_resolution_failure(
        TimeoutError("projection timed out"),
        failure_stage="project_work_item",
    )

    assert classification.failure_stage == "project_work_item"
    assert classification.error_class == "TimeoutError"
    assert classification.failure_class == FailureClass.TIMEOUT
    assert classification.retry_disposition == FailureDisposition.RETRYABLE
    assert classification.failure_code == "timeout_error"


def test_classify_value_error_as_non_retryable_input_invalid() -> None:
    """Validation-style failures should classify as non-retryable input errors."""

    classification = classify_resolution_failure(
        ValueError("invalid fact payload"),
        failure_stage="project_work_item",
    )

    assert classification.error_class == "ValueError"
    assert classification.failure_class == FailureClass.INPUT_INVALID
    assert classification.retry_disposition == FailureDisposition.NON_RETRYABLE
    assert classification.failure_code == "value_error"
