"""Tests for the Phase 2 Resolution Engine runtime shell."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for runtime tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_run_resolution_iteration_claims_and_projects_one_work_item() -> None:
    """One resolution iteration should claim, project, and complete work."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    handled: list[str] = []

    def _projector(row: FactWorkItemRow) -> None:
        handled.append(row.work_item_id)

    processed = run_resolution_iteration(
        queue=queue,
        projector=_projector,
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    assert processed is True
    assert handled == ["work-1"]
    queue.complete_work_item.assert_called_once_with(work_item_id="work-1")


def test_run_resolution_iteration_marks_failures() -> None:
    """One resolution iteration should mark a failed work item retryable."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-2",
        work_type="project-git-facts",
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )

    def _projector(_row: FactWorkItemRow) -> None:
        raise RuntimeError("boom")

    processed = run_resolution_iteration(
        queue=queue,
        projector=_projector,
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    assert processed is True
    queue.fail_work_item.assert_called_once_with(
        work_item_id="work-2",
        error_message="boom",
        terminal=False,
    )
