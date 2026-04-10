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
        status_shared_projection,
        "build_tuning_report",
        lambda *, include_platform=False: {
            "include_platform": include_platform,
            "projection_domains": (
                ["repo_dependency", "workload_dependency"]
                if not include_platform
                else ["platform_infra", "repo_dependency", "workload_dependency"]
            ),
            "recommended": {
                "setting": "4x2",
                "partition_count": 4,
                "batch_limit": 2,
                "round_count": 2,
                "processed_total": 32,
                "peak_pending_total": 32,
                "mean_processed_per_round": 16.0,
            },
        },
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
    assert result["shared_projection_tuning"] == {
        "projection_domains": ["repo_dependency", "workload_dependency"],
        "include_platform": False,
        "current_pending_intents": 2,
        "current_oldest_pending_age_seconds": 33.0,
        "recommended": {
            "setting": "4x2",
            "partition_count": 4,
            "batch_limit": 2,
            "round_count": 2,
            "processed_total": 32,
            "peak_pending_total": 32,
            "mean_processed_per_round": 16.0,
        },
    }
    assert queue.calls == ["run-123"]
    assert shared_store.calls == ["run-123"]


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
        status_shared_projection,
        "build_tuning_report",
        lambda *, include_platform=False: {
            "include_platform": include_platform,
            "projection_domains": (
                ["platform_infra", "repo_dependency", "workload_dependency"]
                if include_platform
                else ["repo_dependency", "workload_dependency"]
            ),
            "recommended": {
                "setting": "4x2",
                "partition_count": 4,
                "batch_limit": 2,
                "round_count": 2,
                "processed_total": 48,
                "peak_pending_total": 48,
                "mean_processed_per_round": 24.0,
            },
        },
    )
    monkeypatch.setattr(
        status_queries, "_checkpoint_status_fallback", lambda _ingester: None
    )

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["shared_projection_tuning"] == {
        "projection_domains": [
            "platform_infra",
            "repo_dependency",
            "workload_dependency",
        ],
        "include_platform": True,
        "current_pending_intents": 1,
        "current_oldest_pending_age_seconds": 12.0,
        "recommended": {
            "setting": "4x2",
            "partition_count": 4,
            "batch_limit": 2,
            "round_count": 2,
            "processed_total": 48,
            "peak_pending_total": 48,
            "mean_processed_per_round": 24.0,
        },
    }
