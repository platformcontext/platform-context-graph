"""Tests for inline shared-followup draining behavior."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace

import pytest

from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for inline shared-followup tests."""

    return datetime(2026, 4, 9, 14, 0, tzinfo=timezone.utc)


class _FakeSharedIntentStore:
    """Minimal in-memory intent store for inline follow-up tests."""

    def __init__(self, rows: list[SharedProjectionIntentRow]) -> None:
        self.rows = list(rows)
        self.completed_ids: set[str] = set()

    def list_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        projection_domain: str | None = None,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        """Return one page of pending intents for a repository and run."""

        pending = [
            row
            for row in self.rows
            if row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and row.intent_id not in self.completed_ids
            and (
                projection_domain is None or row.projection_domain == projection_domain
            )
        ]
        return pending[:limit]

    def count_pending_repository_generation_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        generation_id: str,
        projection_domain: str,
    ) -> int:
        """Return remaining pending intents for one repository generation."""

        return sum(
            1
            for row in self.rows
            if row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and row.generation_id == generation_id
            and row.projection_domain == projection_domain
            and row.intent_id not in self.completed_ids
        )


class _FakeSession:
    """Context-managed fake Neo4j session."""

    def __enter__(self) -> _FakeSession:
        """Enter the fake session context."""

        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        """Exit without suppressing exceptions."""

        del exc_type, exc, tb
        return False


def _fake_builder() -> object:
    """Return a minimal builder whose driver yields one fake session."""

    @contextmanager
    def _session() -> _FakeSession:
        yield _FakeSession()

    return SimpleNamespace(driver=SimpleNamespace(session=_session))


def _intent_rows(count: int) -> list[SharedProjectionIntentRow]:
    """Return deterministic repo-dependency rows for one generation."""

    return [
        SharedProjectionIntentRow(
            intent_id=f"intent-{index}",
            projection_domain="repo_dependency",
            partition_key=f"repo:repository:r_payments->repository:r_users:{index}",
            repository_id="repository:r_payments",
            source_run_id="run-123",
            generation_id="gen-123",
            payload={
                "action": "upsert",
                "repo_id": "repository:r_payments",
                "target_repo_id": f"repository:r_users_{index}",
            },
            created_at=_utc_now(),
            completed_at=None,
        )
        for index in range(count)
    ]


def test_run_inline_shared_followup_drains_multiple_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inline follow-up should keep draining until later pages are cleared."""

    from platform_context_graph.resolution.shared_projection import followup

    store = _FakeSharedIntentStore(_intent_rows(15_050))
    processed_batches: list[int] = []

    def _process_dependency_partition_once(
        _session: object, **_kwargs: object
    ) -> dict[str, int]:
        pending_ids = [
            row.intent_id
            for row in store.rows
            if row.intent_id not in store.completed_ids
        ]
        batch_ids = pending_ids[:2_500]
        store.completed_ids.update(batch_ids)
        processed_batches.append(len(batch_ids))
        return {"processed_intents": len(batch_ids)}

    monkeypatch.setenv("PCG_SHARED_PROJECTION_PARTITION_COUNT", "1")
    monkeypatch.setattr(
        followup,
        "process_dependency_partition_once",
        _process_dependency_partition_once,
    )

    result = followup.run_inline_shared_followup(
        builder=_fake_builder(),
        repository_id="repository:r_payments",
        source_run_id="run-123",
        accepted_generation_id="gen-123",
        authoritative_domains=["repo_dependency"],
        fact_work_queue=object(),
        shared_projection_intent_store=store,
    )

    assert result == {}
    assert processed_batches == [2_500, 2_500, 2_500, 2_500, 2_500, 2_500, 50]
    assert (
        store.count_pending_repository_generation_intents(
            repository_id="repository:r_payments",
            source_run_id="run-123",
            generation_id="gen-123",
            projection_domain="repo_dependency",
        )
        == 0
    )


def test_run_inline_shared_followup_reports_remaining_when_no_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inline follow-up should not spin forever when a partition makes no progress."""

    from platform_context_graph.resolution.shared_projection import followup

    store = _FakeSharedIntentStore(_intent_rows(2))

    monkeypatch.setenv("PCG_SHARED_PROJECTION_PARTITION_COUNT", "1")
    monkeypatch.setattr(
        followup,
        "process_dependency_partition_once",
        lambda _session, **_kwargs: {"processed_intents": 0},
    )

    result = followup.run_inline_shared_followup(
        builder=_fake_builder(),
        repository_id="repository:r_payments",
        source_run_id="run-123",
        accepted_generation_id="gen-123",
        authoritative_domains=["repo_dependency"],
        fact_work_queue=object(),
        shared_projection_intent_store=store,
    )

    assert result == {
        "accepted_generation_id": "gen-123",
        "authoritative_domains": ["repo_dependency"],
    }
