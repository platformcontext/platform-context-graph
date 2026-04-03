"""Tests for persistence of classified resolution failures."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.work_queue.failure_types import FailureClass
from platform_context_graph.facts.work_queue.failure_types import FailureDisposition
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for runtime failure tests."""

    return datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)


def test_run_resolution_iteration_persists_retryable_failure_metadata() -> None:
    """Retryable failures should persist classified stage and disposition fields."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )

    def _projector(_row: FactWorkItemRow) -> None:
        raise TimeoutError("projection timed out")

    processed = run_resolution_iteration(
        queue=queue,
        projector=_projector,
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
        max_attempts=3,
    )

    assert processed is True
    queue.fail_work_item.assert_called_once()
    kwargs = queue.fail_work_item.call_args.kwargs
    assert kwargs["work_item_id"] == "work-1"
    assert kwargs["terminal"] is False
    assert kwargs["failure_stage"] == "project_work_item"
    assert kwargs["error_class"] == "TimeoutError"
    assert kwargs["failure_class"] == FailureClass.TIMEOUT
    assert kwargs["retry_disposition"] == FailureDisposition.RETRYABLE
    assert kwargs["failure_code"] == "timeout_error"


def test_run_resolution_iteration_persists_terminal_failure_metadata() -> None:
    """Terminal failures should preserve non-retryable classification fields."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-2",
        work_type="project-git-facts",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=3,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )

    def _projector(_row: FactWorkItemRow) -> None:
        raise ValueError("invalid fact payload")

    processed = run_resolution_iteration(
        queue=queue,
        projector=_projector,
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
        max_attempts=3,
    )

    assert processed is True
    kwargs = queue.fail_work_item.call_args.kwargs
    assert kwargs["terminal"] is True
    assert kwargs["failure_class"] == FailureClass.INPUT_INVALID
    assert kwargs["retry_disposition"] == FailureDisposition.NON_RETRYABLE
    assert kwargs["failure_code"] == "value_error"
