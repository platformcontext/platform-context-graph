"""Tests for durable shared projection intents in shadow mode."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.resolution.shared_projection.emission import (
    emit_dependency_intents,
)
from platform_context_graph.resolution.shared_projection.emission import (
    emit_platform_infra_intents,
)
from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)
from platform_context_graph.resolution.shared_projection.postgres import (
    PostgresSharedProjectionIntentStore,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for intent tests."""

    return datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)


def test_build_shared_projection_intent_uses_generation_in_identity() -> None:
    """Intent identity should be stable per generation, not just repo/run."""

    first = build_shared_projection_intent(
        projection_domain="platform_infra",
        partition_key="platform:kubernetes:qa",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        generation_id="snapshot-a",
        payload={"platform_id": "platform:kubernetes:qa"},
        created_at=_utc_now(),
    )
    repeat = build_shared_projection_intent(
        projection_domain="platform_infra",
        partition_key="platform:kubernetes:qa",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        generation_id="snapshot-a",
        payload={"platform_id": "platform:kubernetes:qa"},
        created_at=_utc_now(),
    )
    next_generation = build_shared_projection_intent(
        projection_domain="platform_infra",
        partition_key="platform:kubernetes:qa",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        generation_id="snapshot-b",
        payload={"platform_id": "platform:kubernetes:qa"},
        created_at=_utc_now(),
    )

    assert first.intent_id == repeat.intent_id
    assert first.intent_id != next_generation.intent_id


def test_upsert_and_list_shared_projection_intents_round_trip(monkeypatch) -> None:
    """Intent storage should preserve domain, partition, and generation fields."""

    store = PostgresSharedProjectionIntentStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "intent_id": "intent-1",
            "projection_domain": "repo_dependency",
            "partition_key": "repo:r_payments->repository:r_users",
            "repository_id": "repository:r_payments",
            "source_run_id": "run-123",
            "generation_id": "snapshot-abc",
            "payload": {"target_repo_id": "repository:r_users"},
            "created_at": _utc_now(),
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_intents(
        [
            build_shared_projection_intent(
                projection_domain="repo_dependency",
                partition_key="repo:r_payments->repository:r_users",
                repository_id="repository:r_payments",
                source_run_id="run-123",
                generation_id="snapshot-abc",
                payload={"target_repo_id": "repository:r_users"},
                created_at=_utc_now(),
            )
        ]
    )
    intents = store.list_intents(
        repository_id="repository:r_payments",
        source_run_id="run-123",
    )

    query, params = cursor.executemany.call_args.args
    assert "INSERT INTO shared_projection_intents" in query
    assert params[0]["projection_domain"] == "repo_dependency"
    assert params[0]["partition_key"] == "repo:r_payments->repository:r_users"
    assert params[0]["generation_id"] == "snapshot-abc"
    assert intents[0].projection_domain == "repo_dependency"
    assert intents[0].generation_id == "snapshot-abc"


def test_emit_platform_infra_intents_persists_partitioned_shadow_rows() -> None:
    """Infrastructure platform emission should persist one partitioned shadow row."""

    store = MagicMock()

    emit_platform_infra_intents(
        shared_projection_intent_store=store,
        descriptor_rows=[
            {
                "platform_id": "platform:kubernetes:qa",
                "platform_kind": "kubernetes",
                "platform_name": "qa",
                "repo_id": "repository:r_payments",
            }
        ],
        projection_context_by_repo_id={
            "repository:r_payments": {
                "generation_id": "snapshot-abc",
                "source_run_id": "run-123",
            }
        },
        created_at=_utc_now(),
    )

    [rows] = store.upsert_intents.call_args.args
    assert len(rows) == 1
    assert rows[0].projection_domain == "platform_infra"
    assert rows[0].partition_key == "platform:kubernetes:qa"
    assert rows[0].repository_id == "repository:r_payments"
    assert rows[0].source_run_id == "run-123"
    assert rows[0].generation_id == "snapshot-abc"


def test_emit_dependency_intents_persists_repo_and_workload_domains() -> None:
    """Dependency emission should preserve both repo and workload partitions."""

    store = MagicMock()

    emit_dependency_intents(
        shared_projection_intent_store=store,
        repo_dependency_rows=[
            {
                "dependency_name": "users",
                "repo_id": "repository:r_payments",
                "target_repo_id": "repository:r_users",
            }
        ],
        workload_dependency_rows=[
            {
                "dependency_name": "users",
                "repo_id": "repository:r_payments",
                "target_workload_id": "workload:users",
                "workload_id": "workload:payments",
            }
        ],
        projection_context_by_repo_id={
            "repository:r_payments": {
                "generation_id": "snapshot-abc",
                "source_run_id": "run-123",
            }
        },
        created_at=_utc_now(),
    )

    [rows] = store.upsert_intents.call_args.args
    assert [row.projection_domain for row in rows] == [
        "repo_dependency",
        "workload_dependency",
    ]
    assert rows[0].partition_key == "repo:repository:r_payments->repository:r_users"
    assert rows[1].partition_key == "workload:workload:payments->workload:users"
