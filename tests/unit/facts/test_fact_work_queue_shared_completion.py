"""Tests for durable shared-projection completion metadata."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from unittest.mock import MagicMock

import platform_context_graph.facts.work_queue.shared_completion as completion_mod
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue


def _utc_now() -> datetime:
    """Return a stable timestamp for queue shared-completion tests."""

    return datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)


def test_enqueue_work_item_persists_shared_projection_fields(
    monkeypatch,
) -> None:
    """Enqueue should persist shared-projection tracking fields."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    queue.enqueue_work_item(
        FactWorkItemRow(
            work_item_id="work-1",
            work_type="project-git-facts",
            repository_id="repository:r_payments",
            source_run_id="run-123",
            status="awaiting_shared_projection",
            accepted_generation_id="gen-123",
            authoritative_shared_domains=["platform_infra", "repo_dependency"],
            completed_shared_domains=["platform_infra"],
            shared_projection_pending=True,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )

    query, params = cursor.execute.call_args.args
    assert "accepted_generation_id" in query
    assert "authoritative_shared_domains" in query
    assert "completed_shared_domains" in query
    assert "shared_projection_pending" in query
    assert params["accepted_generation_id"] == "gen-123"
    assert params["authoritative_shared_domains"] == [
        "platform_infra",
        "repo_dependency",
    ]
    assert params["completed_shared_domains"] == ["platform_infra"]
    assert params["shared_projection_pending"] is True


def test_mark_shared_projection_pending_sets_waiting_state(monkeypatch) -> None:
    """Marking authoritative shared follow-up should fence completion."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "work_item_id": "work-1",
        "work_type": "project-git-facts",
        "repository_id": "repository:r_payments",
        "source_run_id": "run-123",
        "lease_owner": None,
        "lease_expires_at": None,
        "status": "awaiting_shared_projection",
        "attempt_count": 1,
        "last_error": None,
        "failure_stage": None,
        "error_class": None,
        "failure_class": None,
        "failure_code": None,
        "retry_disposition": None,
        "dead_lettered_at": None,
        "last_attempt_started_at": None,
        "last_attempt_finished_at": _utc_now(),
        "next_retry_at": None,
        "operator_note": None,
        "parent_work_item_id": None,
        "projection_domain": None,
        "accepted_generation_id": "gen-123",
        "authoritative_shared_domains": ["platform_infra"],
        "completed_shared_domains": [],
        "shared_projection_pending": True,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(completion_mod, "utc_now", _utc_now)

    row = queue.mark_shared_projection_pending(
        work_item_id="work-1",
        accepted_generation_id="gen-123",
        authoritative_shared_domains=["platform_infra"],
    )

    query, params = cursor.execute.call_args.args
    assert "status = 'awaiting_shared_projection'" in query
    assert "shared_projection_pending = TRUE" in query
    assert params["accepted_generation_id"] == "gen-123"
    assert params["authoritative_shared_domains"] == ["platform_infra"]
    assert row is not None
    assert row.shared_projection_pending is True


def test_complete_shared_projection_domain_requires_matching_generation(
    monkeypatch,
) -> None:
    """Older child generations should not complete newer accepted parents."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(completion_mod, "utc_now", _utc_now)

    row = queue.complete_shared_projection_domain(
        work_item_id="work-1",
        projection_domain="platform_infra",
        accepted_generation_id="gen-stale",
    )

    query, params = cursor.execute.call_args.args
    assert "accepted_generation_id = %(accepted_generation_id)s" in query
    assert params["accepted_generation_id"] == "gen-stale"
    assert params["projection_domain"] == "platform_infra"
    assert row is None
