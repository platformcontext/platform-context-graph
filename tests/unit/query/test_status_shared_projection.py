"""Tests for shared-projection-aware ingester status surfaces."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from platform_context_graph.query import status as status_queries
from platform_context_graph.query import status_shared_projection


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


class _SharedStore:
    enabled = True

    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.calls: list[str | None] = []

    def list_pending_backlog_snapshot(
        self, *, source_run_id: str | None = None
    ) -> list[object]:
        self.calls.append(source_run_id)
        return list(self.rows)


class _DecisionStore:
    enabled = True


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
    shared_store = _SharedStore(
        [
            {
                "projection_domain": "repo_dependency",
                "pending_depth": 2,
                "oldest_age_seconds": 33.0,
            }
        ]
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: queue)
    monkeypatch.setattr(
        status_queries,
        "get_shared_projection_intent_store",
        lambda: shared_store,
    )
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
    assert result["shared_projection_backlog"] == [
        {
            "projection_domain": "repo_dependency",
            "pending_intents": 2,
            "oldest_pending_age_seconds": 33.0,
        }
    ]
    # Tuning is now handled by Go data plane, so it returns None
    assert result["shared_projection_tuning"] is None
    assert queue.calls == ["run-123"]
    assert shared_store.calls == ["run-123"]


def test_get_ingester_status_surfaces_reducer_truth_summary(
    monkeypatch,
) -> None:
    """Status should expose a compact reducer-health rollup."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "completed",
                "finalization_status": "completed",
                "active_run_id": "run-456",
                "repository_count": 4,
                "pending_repositories": 0,
                "completed_repositories": 4,
                "failed_repositories": 0,
                "updated_at": datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    queue = _Queue(pending_count=3)
    shared_store = _SharedStore(
        [
            {
                "projection_domain": "repo_dependency",
                "pending_depth": 2,
                "oldest_age_seconds": 22.0,
            },
            {
                "projection_domain": "platform_infra",
                "pending_depth": 1,
                "oldest_age_seconds": 33.0,
            },
        ]
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: queue)
    monkeypatch.setattr(status_queries, "get_shared_projection_intent_store", lambda: shared_store)
    monkeypatch.setattr(
        status_queries, "get_projection_decision_store", lambda: _DecisionStore()
    )
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["truth_summary"] == {
        "state": "degraded",
        "reducer_queue_available": True,
        "projection_decision_store_available": True,
        "pending_reducer_work_items": 3,
        "shared_projection_backlog_count": 2,
        "shared_projection_domains": [
            "repo_dependency",
            "platform_infra",
        ],
        "shared_projection_oldest_pending_age_seconds": 33.0,
        "reason": (
            "3 reducer work item(s) still awaiting follow-up; "
            "2 shared projection domain(s) still pending"
        ),
    }


def test_get_ingester_status_marks_truth_summary_unknown_when_support_missing(
    monkeypatch,
) -> None:
    """Status should admit when the reducer truth plane is unavailable."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "idle",
                "repository_count": 0,
                "pending_repositories": 0,
                "completed_repositories": 0,
                "failed_repositories": 0,
                "updated_at": datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: None)
    monkeypatch.setattr(
        status_queries,
        "get_shared_projection_intent_store",
        lambda: _SharedStore([]),
    )
    monkeypatch.setattr(
        status_queries, "get_projection_decision_store", lambda: None
    )
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["truth_summary"] == {
        "state": "unknown",
        "reducer_queue_available": False,
        "projection_decision_store_available": False,
        "pending_reducer_work_items": 0,
        "shared_projection_backlog_count": 0,
        "shared_projection_domains": [],
        "shared_projection_oldest_pending_age_seconds": 0.0,
        "reason": "reducer queue and projection decision store are unavailable",
    }


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
        status_queries,
        "get_shared_projection_intent_store",
        lambda: _SharedStore([]),
    )
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "idle"
    assert result["shared_projection_pending_repositories"] == 0
    assert result["shared_projection_backlog"] == []
    assert result["shared_projection_tuning"] is None
    assert queue.calls == []


def test_get_ingester_status_preserves_existing_shared_pending_when_queue_unavailable(
    monkeypatch,
) -> None:
    """Status should preserve known shared pending state without a fresh queue."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "completed",
                "finalization_status": "completed",
                "active_phase": "awaiting_shared_projection",
                "active_run_id": "run-123",
                "repository_count": 4,
                "pending_repositories": 1,
                "completed_repositories": 3,
                "failed_repositories": 0,
                "shared_projection_pending_repositories": 2,
                "updated_at": datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            }
        }
    )
    shared_store = _SharedStore(
        [
            {
                "projection_domain": "platform_runtime",
                "pending_depth": 4,
                "oldest_age_seconds": 12.0,
            }
        ]
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: None)
    monkeypatch.setattr(
        status_queries,
        "get_shared_projection_intent_store",
        lambda: shared_store,
    )
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["status"] == "completed"
    assert result["active_phase"] == "awaiting_shared_projection"
    assert result["shared_projection_pending_repositories"] == 2
    assert result["shared_projection_backlog"] == [
        {
            "projection_domain": "platform_runtime",
            "pending_intents": 4,
            "oldest_pending_age_seconds": 12.0,
        }
    ]
    assert result["pending_repositories"] == 1
    assert result["completed_repositories"] == 3
    assert shared_store.calls == ["run-123"]


def test_get_ingester_status_uses_platform_tuning_when_platform_backlog_present(
    monkeypatch,
) -> None:
    """Status should expand the tuning recommendation for platform backlog."""

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
    queue = _Queue(pending_count=1)
    shared_store = _SharedStore(
        [
            {
                "projection_domain": "platform_infra",
                "pending_depth": 1,
                "oldest_age_seconds": 12.0,
            }
        ]
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)
    monkeypatch.setattr(status_queries, "get_fact_work_queue", lambda: queue)
    monkeypatch.setattr(
        status_queries,
        "get_shared_projection_intent_store",
        lambda: shared_store,
    )
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    # Tuning is now handled by Go data plane, so it returns None
    assert result["shared_projection_tuning"] is None
