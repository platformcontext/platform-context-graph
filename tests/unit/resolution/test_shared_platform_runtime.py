"""Tests for partitioned shared platform projection runtime."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timezone
from pathlib import Path
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
    """Return a stable UTC timestamp for shared-platform runtime tests."""

    return datetime(2026, 4, 9, 12, minute, tzinfo=timezone.utc)


class _FakeResult:
    """Minimal query result wrapper with ``data`` support."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, Any]]:
        """Return fake query rows."""

        return self._rows


class _FakeSession:
    """Minimal session stub for platform runtime tests."""

    def __init__(
        self,
        *,
        repo_rows: list[dict[str, Any]] | None = None,
        platform_rows: list[dict[str, Any]] | None = None,
        existing_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.repo_rows = repo_rows or []
        self.platform_rows = platform_rows or []
        self.existing_rows = existing_rows or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> _FakeResult:
        """Record the query and return matching fake rows."""

        self.calls.append((query, params))
        if "existing_platform_id" in query:
            return _FakeResult(self.existing_rows)
        if "RETURN repo.id as repo_id," in query:
            return _FakeResult(self.platform_rows)
        if "RETURN repo.id as repo_id" in query:
            return _FakeResult(self.repo_rows)
        return _FakeResult([])


class _FakeIntentStore:
    """Minimal durable intent store for worker-runtime tests."""

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
        self, *, projection_domain: str, limit: int = 100
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


def test_materialize_infrastructure_platforms_uses_worker_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker cutover should emit intents and skip inline shared graph writes."""

    from platform_context_graph.resolution import platforms as platform_mod

    session = _FakeSession(
        repo_rows=[{"repo_id": "repository:r_123"}],
        platform_rows=[
            {
                "repo_id": "repository:r_123",
                "repo_name": "payments",
                "data_types": ["terraform_remote_state"],
                "data_names": ["qa"],
                "module_sources": ["terraform-aws-modules/eks/aws"],
                "module_names": ["cluster"],
                "resource_types": ["aws_eks_cluster"],
                "resource_names": ["payments"],
            }
        ],
        existing_rows=[
            {
                "repo_id": "repository:r_123",
                "existing_platform_id": "platform:kubernetes:old",
            }
        ],
    )
    emitted: list[list[dict[str, object]]] = []
    monkeypatch.setattr(
        platform_mod,
        "platform_shared_projection_worker_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        platform_mod,
        "emit_platform_infra_intents",
        lambda **kwargs: emitted.append(kwargs["descriptor_rows"]),
    )
    monkeypatch.setattr(
        platform_mod,
        "retract_infrastructure_platform_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inline retract should not run in worker cutover")
        ),
    )
    monkeypatch.setattr(
        platform_mod,
        "write_infrastructure_platform_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inline writes should not run in worker cutover")
        ),
    )

    metrics = platform_mod.materialize_infrastructure_platforms_for_repo_paths(
        session,
        repo_paths=[Path("/tmp/infra")],
        projection_context_by_repo_id={
            "repository:r_123": {
                "generation_id": "gen-123",
                "source_run_id": "run-123",
            }
        },
        shared_projection_intent_store=MagicMock(),
    )

    assert emitted
    flattened = emitted[0]
    assert {str(row["action"]) for row in flattened} == {"retract", "upsert"}
    assert metrics["shared_projection"]["authoritative_domains"] == ["platform_infra"]
    assert metrics["shared_projection"]["accepted_generation_id"] == "gen-123"
    assert metrics["infrastructure_platform_edges_projected"] == 0


def test_process_platform_partition_once_applies_latest_generation_only() -> None:
    """The worker should apply only the newest generation per repo/platform pair."""

    from platform_context_graph.resolution.shared_projection.partitioning import (
        partition_for_key,
    )
    from platform_context_graph.resolution.shared_projection.runtime import (
        process_platform_partition_once,
    )

    old_intent = build_shared_projection_intent(
        projection_domain="platform_infra",
        partition_key="platform:kubernetes:qa",
        repository_id="repository:r_payments",
        source_run_id="run-123",
        generation_id="gen-old",
        payload={
            "action": "upsert",
            "platform_id": "platform:kubernetes:qa",
            "platform_kind": "kubernetes",
            "platform_name": "qa-old",
            "platform_provider": None,
            "platform_environment": "qa",
            "platform_region": None,
            "platform_locator": None,
            "repo_id": "repository:r_payments",
        },
        created_at=_utc_now(0),
    )
    new_intent = replace(
        build_shared_projection_intent(
            projection_domain="platform_infra",
            partition_key="platform:kubernetes:qa",
            repository_id="repository:r_payments",
            source_run_id="run-123",
            generation_id="gen-new",
            payload={
                "action": "upsert",
                "platform_id": "platform:kubernetes:qa",
                "platform_kind": "kubernetes",
                "platform_name": "qa-new",
                "platform_provider": None,
                "platform_environment": "qa",
                "platform_region": None,
                "platform_locator": None,
                "repo_id": "repository:r_payments",
            },
            created_at=_utc_now(1),
        ),
        created_at=_utc_now(1),
    )
    store = _FakeIntentStore([old_intent, new_intent])
    queue = MagicMock()
    queue.list_shared_projection_acceptances.return_value = {
        ("repository:r_payments", "run-123"): "gen-new"
    }
    session = MagicMock()
    partition_id = partition_for_key("platform:kubernetes:qa", partition_count=8)

    metrics = process_platform_partition_once(
        session,
        shared_projection_intent_store=store,
        fact_work_queue=queue,
        partition_id=partition_id,
        partition_count=8,
        lease_owner="worker-1",
        lease_ttl_seconds=60,
    )

    retract_call = session.run.call_args_list[0]
    write_call = session.run.call_args_list[1]
    assert retract_call.kwargs["rows"] == [
        {
            "platform_id": "platform:kubernetes:qa",
            "repo_id": "repository:r_payments",
        }
    ]
    assert write_call.kwargs["rows"][0]["platform_name"] == "qa-new"
    assert set(store.completed_ids) == {old_intent.intent_id, new_intent.intent_id}
    queue.complete_shared_projection_domain_by_generation.assert_called_once_with(
        repository_id="repository:r_payments",
        source_run_id="run-123",
        accepted_generation_id="gen-new",
        projection_domain="platform_infra",
    )
    assert metrics["processed_intents"] == 2
