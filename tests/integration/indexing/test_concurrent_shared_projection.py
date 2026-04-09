"""Integration checks for shared dependency projection convergence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timezone
from unittest.mock import MagicMock

from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)


def _utc_now(minute: int = 0) -> datetime:
    """Return a stable UTC timestamp for shared-projection tests."""

    return datetime(2026, 4, 9, 14, minute, tzinfo=timezone.utc)


class _CollectingIntentStore:
    """Collect emitted intents and support one-pass worker processing."""

    def __init__(self) -> None:
        self.rows: list[SharedProjectionIntentRow] = []
        self.completed_ids: list[str] = []

    def upsert_intents(self, rows: list[SharedProjectionIntentRow]) -> None:
        existing = {row.intent_id: row for row in self.rows}
        for row in rows:
            existing[row.intent_id] = row
        self.rows = list(existing.values())

    def claim_partition_lease(self, **_kwargs: object) -> bool:
        return True

    def release_partition_lease(self, **_kwargs: object) -> None:
        return None

    def list_pending_domain_intents(
        self,
        *,
        projection_domain: str,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        pending = [
            row
            for row in self.rows
            if row.projection_domain == projection_domain
            and row.intent_id not in self.completed_ids
        ]
        return pending[:limit]

    def mark_intents_completed(self, *, intent_ids: list[str]) -> None:
        self.completed_ids.extend(intent_ids)

    def count_pending_repository_generation_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        generation_id: str,
        projection_domain: str,
    ) -> int:
        return sum(
            1
            for row in self.rows
            if row.intent_id not in self.completed_ids
            and row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and row.generation_id == generation_id
            and row.projection_domain == projection_domain
        )


def test_dependency_worker_converges_to_latest_generation_only(monkeypatch) -> None:
    """Newer generations should supersede older dependency intents cleanly."""

    from platform_context_graph.resolution.shared_projection.runtime import (
        process_dependency_partition_once,
    )
    from platform_context_graph.resolution.workloads import dependency_support

    store = _CollectingIntentStore()
    monkeypatch.setattr(
        dependency_support,
        "dependency_shared_projection_worker_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        dependency_support,
        "existing_repo_dependency_rows",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        dependency_support,
        "existing_workload_dependency_rows",
        lambda *_args, **_kwargs: [],
    )

    generation_rows = [
        (
            "gen-old",
            [
                {
                    "dependency_name": "legacy",
                    "repo_id": "repository:r_payments",
                    "target_repo_id": "repository:r_legacy",
                }
            ],
            [
                {
                    "dependency_name": "legacy",
                    "repo_id": "repository:r_payments",
                    "target_workload_id": "workload:legacy",
                    "workload_id": "workload:payments",
                }
            ],
        ),
        (
            "gen-new",
            [
                {
                    "dependency_name": "users",
                    "repo_id": "repository:r_payments",
                    "target_repo_id": "repository:r_users",
                }
            ],
            [
                {
                    "dependency_name": "users",
                    "repo_id": "repository:r_payments",
                    "target_workload_id": "workload:users",
                    "workload_id": "workload:payments",
                }
            ],
        ),
    ]

    for generation_id, repo_rows, workload_rows in generation_rows:
        dependency_support.materialize_runtime_dependencies(
            MagicMock(),
            repo_descriptors=[
                {
                    "repo_id": "repository:r_payments",
                    "repo_name": "payments",
                    "workload_id": "workload:payments",
                }
            ],
            evidence_source="finalization/workloads",
            projection_context_by_repo_id={
                "repository:r_payments": {
                    "generation_id": generation_id,
                    "source_run_id": "run-123",
                }
            },
            shared_projection_intent_store=store,
            load_runtime_dependency_targets_fn=lambda *_args, repo_rows=repo_rows, workload_rows=workload_rows, **_kwargs: (
                repo_rows,
                workload_rows,
            ),
        )

    queue = MagicMock()
    queue.list_shared_projection_acceptances.return_value = {
        ("repository:r_payments", "run-123"): "gen-new"
    }
    session = MagicMock()

    repo_metrics = process_dependency_partition_once(
        session,
        shared_projection_intent_store=store,
        fact_work_queue=queue,
        projection_domain="repo_dependency",
        partition_id=0,
        partition_count=1,
        lease_owner="worker-1",
        lease_ttl_seconds=60,
    )
    workload_metrics = process_dependency_partition_once(
        session,
        shared_projection_intent_store=store,
        fact_work_queue=queue,
        projection_domain="workload_dependency",
        partition_id=0,
        partition_count=1,
        lease_owner="worker-1",
        lease_ttl_seconds=60,
    )

    written_rows = [
        kwargs["rows"]
        for _, kwargs in session.run.call_args_list
        if "rows" in kwargs and kwargs["rows"]
    ]
    flattened = [row for rows in written_rows for row in rows]
    assert all(row.get("dependency_name") != "legacy" for row in flattened)
    assert any(row.get("dependency_name") == "users" for row in flattened)
    assert repo_metrics["processed_intents"] == 2
    assert workload_metrics["processed_intents"] == 2
