"""Tests for ingester inline projection failure classification."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from platform_context_graph.facts.emission.git_snapshot import (
    GitSnapshotFactEmissionResult,
)
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.stages import (
    PROJECT_PLATFORMS_STAGE,
)
from platform_context_graph.facts.work_queue.stages import ProjectionStageError
from platform_context_graph.indexing.coordinator_facts import (
    commit_repository_snapshot_from_facts,
)


class TransientError(Exception):
    """Small Neo4j-like transient error used for unit tests."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for inline projection tests."""

    return datetime(2026, 4, 9, 13, 0, tzinfo=timezone.utc)


def test_commit_repository_snapshot_from_facts_classifies_deadlock_failures(
    tmp_path: Path,
) -> None:
    """Inline projection should persist the same deadlock metadata as runtime."""

    repo_path = tmp_path / "payments"
    snapshot = SimpleNamespace(
        repo_path=str(repo_path),
        file_count=1,
        imports_map={},
        file_data=[],
    )
    work_item = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="repository:r_123",
        source_run_id="run-123",
        status="leased",
        lease_owner="indexing",
        lease_expires_at=_utc_now(),
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    work_queue = MagicMock()
    work_queue.lease_work_item.return_value = work_item
    deadlock_error = TransientError(
        code="Neo.TransientError.Transaction.DeadlockDetected",
        message="Deadlock detected while trying to acquire locks.",
    )

    with pytest.raises(ProjectionStageError, match="Deadlock detected"):
        commit_repository_snapshot_from_facts(
            builder=SimpleNamespace(_content_provider=SimpleNamespace(enabled=False)),
            snapshot=snapshot,
            fact_emission_result=GitSnapshotFactEmissionResult(
                repository_id="repository:r_123",
                source_run_id="run-123",
                source_snapshot_id="snapshot-abc",
                work_item_id="work-1",
                fact_count=3,
            ),
            fact_store=MagicMock(),
            work_queue=work_queue,
            graph_store=SimpleNamespace(delete_repository=MagicMock()),
            project_work_item_fn=MagicMock(
                side_effect=ProjectionStageError(
                    PROJECT_PLATFORMS_STAGE,
                    deadlock_error,
                )
            ),
            lease_owner="indexing-worker",
            lease_ttl_seconds=60,
            warning_logger_fn=lambda *_args, **_kwargs: None,
        )

    kwargs = work_queue.fail_work_item.call_args.kwargs
    assert kwargs["work_item_id"] == "work-1"
    assert kwargs["terminal"] is False
    assert kwargs["failure_stage"] == PROJECT_PLATFORMS_STAGE
    assert kwargs["error_class"] == "TransientError"
    assert kwargs["failure_code"] == "neo_transient_error_transaction_deadlock_detected"
    assert kwargs["retry_disposition"] == "retryable"
    assert kwargs["next_retry_at"] is not None
