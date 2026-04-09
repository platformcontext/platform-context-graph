"""Tests for partitioned shared dependency projection runtime."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)


def _utc_now(minute: int = 0) -> datetime:
    """Return a stable UTC timestamp for shared-dependency runtime tests."""

    return datetime(2026, 4, 9, 13, minute, tzinfo=timezone.utc)


class _FakeIntentStore:
    """Minimal durable intent store for shared-dependency runtime tests."""

    def __init__(self, rows: list[SharedProjectionIntentRow]) -> None:
        self.rows = list(rows)
        self.completed_ids: list[str] = []
        self.lease_requests: list[dict[str, object]] = []
        self.released: list[dict[str, object]] = []

    def claim_partition_lease(
        self,
        *,
        projection_domain: str,
        partition_id: int,
        partition_count: int,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> bool:
        self.lease_requests.append(
            {
                "projection_domain": projection_domain,
                "partition_id": partition_id,
                "partition_count": partition_count,
                "lease_owner": lease_owner,
                "lease_ttl_seconds": lease_ttl_seconds,
            }
        )
        return True

    def release_partition_lease(
        self,
        *,
        projection_domain: str,
        partition_id: int,
        partition_count: int,
        lease_owner: str,
    ) -> None:
        self.released.append(
            {
                "projection_domain": projection_domain,
                "partition_id": partition_id,
                "partition_count": partition_count,
                "lease_owner": lease_owner,
            }
        )

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


def test_materialize_runtime_dependencies_uses_worker_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker cutover should emit authoritative dependency intents only."""

    from platform_context_graph.resolution.workloads import dependency_support

    monkeypatch.setattr(
        dependency_support,
        "dependency_shared_projection_worker_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        dependency_support,
        "_load_runtime_dependency_targets",
        lambda *_args, **_kwargs: (
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
    )
    monkeypatch.setattr(
        dependency_support,
        "existing_repo_dependency_rows",
        lambda *_args, **_kwargs: [
            {
                "repo_id": "repository:r_payments",
                "target_repo_id": "repository:r_legacy",
            }
        ],
    )
    monkeypatch.setattr(
        dependency_support,
        "existing_workload_dependency_rows",
        lambda *_args, **_kwargs: [
            {
                "repo_id": "repository:r_payments",
                "target_workload_id": "workload:legacy",
                "workload_id": "workload:payments",
            }
        ],
    )
    monkeypatch.setattr(
        dependency_support,
        "write_repo_dependency_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inline repo dependency writes should not run")
        ),
    )
    monkeypatch.setattr(
        dependency_support,
        "write_workload_dependency_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inline workload dependency writes should not run")
        ),
    )
    store = MagicMock()

    metrics = dependency_support.materialize_runtime_dependencies(
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
                "generation_id": "gen-123",
                "source_run_id": "run-123",
            }
        },
        shared_projection_intent_store=store,
    )

    [rows] = store.upsert_intents.call_args.args
    assert sorted(row.projection_domain for row in rows) == [
        "repo_dependency",
        "repo_dependency",
        "workload_dependency",
        "workload_dependency",
    ]
    assert sorted(str(row.payload["action"]) for row in rows) == [
        "retract",
        "retract",
        "upsert",
        "upsert",
    ]
    assert metrics["repo_dependency_edges_projected"] == 0
    assert metrics["workload_dependency_edges_projected"] == 0
    assert metrics["shared_projection"]["authoritative_domains"] == [
        "repo_dependency",
        "workload_dependency",
    ]


def test_process_dependency_partition_once_ignores_stale_generations() -> None:
    """The worker should discard stale generations before applying one edge."""

    from platform_context_graph.resolution.shared_projection.partitioning import (
        partition_for_key,
    )
    from platform_context_graph.resolution.shared_projection.runtime import (
        process_dependency_partition_once,
    )

    stale_matching = build_shared_projection_intent(
        projection_domain="repo_dependency",
        partition_key="repo:repository:r_payments->repository:r_users",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        generation_id="gen-old",
        payload={
            "action": "upsert",
            "dependency_name": "users",
            "repo_id": "repository:r_payments",
            "target_repo_id": "repository:r_users",
        },
        created_at=_utc_now(0),
    )
    stale_other_key = build_shared_projection_intent(
        projection_domain="repo_dependency",
        partition_key="repo:repository:r_payments->repository:r_legacy",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        generation_id="gen-old",
        payload={
            "action": "upsert",
            "dependency_name": "legacy",
            "repo_id": "repository:r_payments",
            "target_repo_id": "repository:r_legacy",
        },
        created_at=_utc_now(0),
    )
    active = replace(
        build_shared_projection_intent(
            projection_domain="repo_dependency",
            partition_key="repo:repository:r_payments->repository:r_users",
            repository_id="repository:r_payments",
            source_run_id="run-123",
            generation_id="gen-new",
            payload={
                "action": "upsert",
                "dependency_name": "users",
                "repo_id": "repository:r_payments",
                "target_repo_id": "repository:r_users",
            },
            created_at=_utc_now(1),
        ),
        created_at=_utc_now(1),
    )
    store = _FakeIntentStore([stale_matching, stale_other_key, active])
    queue = MagicMock()
    queue.list_shared_projection_acceptances.return_value = {
        ("repository:r_payments", "run-123"): "gen-new"
    }
    session = MagicMock()
    partition_id = partition_for_key(
        "repo:repository:r_payments->repository:r_users", partition_count=1
    )

    metrics = process_dependency_partition_once(
        session,
        shared_projection_intent_store=store,
        fact_work_queue=queue,
        projection_domain="repo_dependency",
        partition_id=partition_id,
        partition_count=1,
        lease_owner="worker-1",
        lease_ttl_seconds=60,
    )

    retract_call = session.run.call_args_list[0]
    write_call = session.run.call_args_list[1]
    assert retract_call.kwargs["rows"] == [
        {
            "repo_id": "repository:r_payments",
            "target_repo_id": "repository:r_users",
        }
    ]
    assert write_call.kwargs["rows"] == [
        {
            "action": "upsert",
            "dependency_name": "users",
            "repo_id": "repository:r_payments",
            "target_repo_id": "repository:r_users",
        }
    ]
    assert set(store.completed_ids) == {
        stale_matching.intent_id,
        stale_other_key.intent_id,
        active.intent_id,
    }
    queue.complete_shared_projection_domain_by_generation.assert_called_once_with(
        repository_id="repository:r_payments",
        source_run_id="run-123",
        accepted_generation_id="gen-new",
        projection_domain="repo_dependency",
    )
    assert metrics["processed_intents"] == 3
