"""Integration checks for split-runtime shared projection equivalence."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import datetime
from datetime import timezone
from typing import Any
from unittest.mock import MagicMock

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.resolution.orchestration.engine import project_work_item
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
)
from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)


def _utc_now(minute: int = 0) -> datetime:
    """Return a stable UTC timestamp for split-runtime integration tests."""

    return datetime(2026, 4, 9, 15, minute, tzinfo=timezone.utc)


class _InMemorySharedIntentStore:
    """In-memory shared intent store that mimics the worker contract."""

    def __init__(self, rows: list[SharedProjectionIntentRow]) -> None:
        self.rows = list(rows)
        self.completed_ids: list[str] = []

    def list_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        projection_domain: str | None = None,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        rows = [
            row
            for row in self.rows
            if row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and (
                projection_domain is None or row.projection_domain == projection_domain
            )
        ]
        return rows[:limit]

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
        return [
            row
            for row in self.rows
            if row.projection_domain == projection_domain
            and row.completed_at is None
            and row.intent_id not in self.completed_ids
        ][:limit]

    def mark_intents_completed(self, *, intent_ids: list[str]) -> None:
        self.completed_ids.extend(intent_ids)
        updated_rows: list[SharedProjectionIntentRow] = []
        for row in self.rows:
            if row.intent_id in intent_ids:
                updated_rows.append(replace(row, completed_at=_utc_now(5)))
            else:
                updated_rows.append(row)
        self.rows = updated_rows

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


class _FakeSession:
    """Minimal session that records graph writes for equivalence checks."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, object]]:
        self.calls.append((query, params))
        return []


class _SessionContext(AbstractContextManager["_FakeSession"]):
    """Context wrapper returning one fake session instance."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __enter__(self) -> _FakeSession:
        return self._session

    def __exit__(self, *_args: object) -> None:
        return None


class _ResolutionQueue:
    """Minimal in-memory queue for resolution-runtime equivalence tests."""

    def __init__(self, row: FactWorkItemRow) -> None:
        self.row = row
        self.claimed = False
        self.completed_work_item_id: str | None = None
        self.pending_calls: list[dict[str, object]] = []
        self.domain_completion_calls: list[dict[str, object]] = []

    def claim_work_item(
        self,
        *,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        del lease_ttl_seconds
        if self.claimed:
            return None
        self.claimed = True
        self.row = replace(self.row, lease_owner=lease_owner, status="leased")
        return self.row

    def complete_work_item(self, *, work_item_id: str) -> None:
        self.completed_work_item_id = work_item_id

    def mark_shared_projection_pending(self, **kwargs: object) -> None:
        self.pending_calls.append(dict(kwargs))

    def complete_shared_projection_domain_by_generation(self, **kwargs: object) -> None:
        self.domain_completion_calls.append(dict(kwargs))

    def list_shared_projection_acceptances(
        self,
        *,
        projection_domain: str,
        repository_ids: list[str] | None = None,
    ) -> dict[tuple[str, str], str]:
        del projection_domain
        del repository_ids
        return {("github.com/acme/service", "run-123"): "snapshot-abc"}

    def fail_work_item(self, **_kwargs: object) -> None:
        raise AssertionError("resolution iteration should not fail in this test")

    def list_queue_snapshot(self) -> list[object]:
        return []


def _fact_store() -> MagicMock:
    """Return a fact store with one file fact for engine projection."""

    store = MagicMock()
    store.list_facts.return_value = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"language": "python", "is_dependency": False},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]
    return store


def _shared_store() -> _InMemorySharedIntentStore:
    """Return a shared intent store seeded with one dependency intent."""

    return _InMemorySharedIntentStore(
        [
            build_shared_projection_intent(
                projection_domain="repo_dependency",
                partition_key="repo:github.com/acme/service->repository:r_users",
                repository_id="github.com/acme/service",
                source_run_id="run-123",
                generation_id="snapshot-abc",
                payload={
                    "action": "upsert",
                    "dependency_name": "users",
                    "repo_id": "github.com/acme/service",
                    "target_repo_id": "repository:r_users",
                },
                created_at=_utc_now(),
            )
        ]
    )


def _build_projector(
    *,
    builder: Any,
    fact_store: Any,
    queue: Any,
    shared_store: Any,
) -> Any:
    """Return one projector wrapper using the common engine path."""

    return lambda work_item: project_work_item(
        work_item,
        builder=builder,
        fact_store=fact_store,
        fact_work_queue=queue,
        shared_projection_intent_store=shared_store,
        fact_projector=lambda **_kwargs: {"files": 1},
        relationship_projector=lambda **_kwargs: {"imports": 0},
        workload_projector=lambda **_kwargs: {
            "workloads_projected": 1,
            "shared_projection": {
                "authoritative_domains": ["repo_dependency"],
                "accepted_generation_id": "snapshot-abc",
            },
        },
        platform_projector=lambda **_kwargs: {
            "infrastructure_platform_edges_projected": 0
        },
    )


def test_split_runtime_entrypoints_converge_after_inline_followup() -> None:
    """Ingester-inline and resolution-runtime should drain shared follow-up equally."""

    shared_store_inline = _shared_store()
    inline_session = _FakeSession()
    inline_builder = MagicMock()
    inline_builder.driver.session.return_value = _SessionContext(inline_session)
    inline_builder.reset_repository_subtree_in_graph = MagicMock()
    inline_builder._content_provider = MagicMock(enabled=False)
    inline_queue = MagicMock()
    inline_queue.complete_shared_projection_domain_by_generation = MagicMock()
    inline_queue.list_shared_projection_acceptances.return_value = {
        ("github.com/acme/service", "run-123"): "snapshot-abc"
    }

    inline_metrics = _build_projector(
        builder=inline_builder,
        fact_store=_fact_store(),
        queue=inline_queue,
        shared_store=shared_store_inline,
    )(
        FactWorkItemRow(
            work_item_id="work-inline",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
        )
    )

    shared_store_runtime = _shared_store()
    runtime_session = _FakeSession()
    runtime_builder = MagicMock()
    runtime_builder.driver.session.return_value = _SessionContext(runtime_session)
    runtime_builder.reset_repository_subtree_in_graph = MagicMock()
    runtime_builder._content_provider = MagicMock(enabled=False)
    runtime_queue = _ResolutionQueue(
        FactWorkItemRow(
            work_item_id="work-runtime",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )

    processed = run_resolution_iteration(
        queue=runtime_queue,
        projector=_build_projector(
            builder=runtime_builder,
            fact_store=_fact_store(),
            queue=runtime_queue,
            shared_store=shared_store_runtime,
        ),
        lease_owner="resolution-engine",
        lease_ttl_seconds=60,
    )

    assert "shared_projection" not in inline_metrics
    assert processed is True
    assert runtime_queue.completed_work_item_id == "work-runtime"
    assert not runtime_queue.pending_calls
    assert inline_queue.complete_shared_projection_domain_by_generation.called
    assert runtime_queue.domain_completion_calls
    assert len(inline_session.calls) == len(runtime_session.calls)
