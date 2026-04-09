"""Tests for shared-projection-aware ingester status surfaces."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from platform_context_graph.query import status as status_queries


class _Store:
    enabled = True

    def __init__(self, payload: dict[str, dict[str, object]]) -> None:
        self._payload = payload

    def get_runtime_status(self, *, ingester: str):
        return self._payload.get(ingester)


class _Queue:
    enabled = True

    def __init__(self, pending_count: int) -> None:
        self.pending_count = pending_count
        self.calls: list[str | None] = []

    def count_shared_projection_pending(
        self, *, source_run_id: str | None = None
    ) -> int:
        self.calls.append(source_run_id)
        return self.pending_count


def test_get_ingester_status_surfaces_shared_projection_pending(
    monkeypatch,
) -> None:
    """Completed runs should stay in-progress while shared follow-up is pending."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "completed",
                "finalization_status": "completed",
                "active_run_id": "run-123",
                "repository_count": 4,
                "pending_repositories": 0,
                "completed_repositories": 4,
                "failed_repositories": 0,
                "updated_at": datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    queue = _Queue(pending_count=2)
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: queue)
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "indexing"
    assert result["finalization_status"] == "running"
    assert result["active_phase"] == "awaiting_shared_projection"
    assert result["shared_projection_pending_repositories"] == 2
    assert result["pending_repositories"] == 2
    assert result["completed_repositories"] == 2
    assert queue.calls == ["run-123"]


def test_get_ingester_status_ignores_shadow_pending_without_active_run(
    monkeypatch,
) -> None:
    """Status should not probe queue state when no active run is available."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "idle",
                "active_run_id": None,
                "repository_count": 0,
                "pending_repositories": 0,
                "completed_repositories": 0,
                "failed_repositories": 0,
                "updated_at": datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    queue = _Queue(pending_count=5)
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: queue)
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "idle"
    assert result["shared_projection_pending_repositories"] == 0
    assert queue.calls == []
