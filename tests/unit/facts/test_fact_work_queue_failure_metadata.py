"""Tests for durable fact work queue failure metadata."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import platform_context_graph.facts.work_queue.claims as claims_mod
from platform_context_graph.facts.work_queue.failure_types import FailureClass
from platform_context_graph.facts.work_queue.failure_types import FailureDisposition
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for queue failure tests."""

    return datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)


def test_enqueue_work_item_persists_failure_metadata_fields(
    monkeypatch,
) -> None:
    """Enqueue should write the durable failure metadata columns."""

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
            status="failed",
            attempt_count=2,
            last_error="boom",
            failure_stage="project_work_item",
            error_class="RuntimeError",
            failure_class=FailureClass.PROJECTION_BUG,
            failure_code="runtime_error",
            retry_disposition=FailureDisposition.MANUAL_REVIEW,
            dead_lettered_at=_utc_now(),
            last_attempt_started_at=_utc_now(),
            last_attempt_finished_at=_utc_now(),
            next_retry_at=None,
            operator_note="operator replay required",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )

    query, params = cursor.execute.call_args.args
    assert "failure_stage" in query
    assert "failure_class" in query
    assert params["failure_stage"] == "project_work_item"
    assert params["error_class"] == "RuntimeError"
    assert params["failure_class"] == FailureClass.PROJECTION_BUG
    assert params["retry_disposition"] == FailureDisposition.MANUAL_REVIEW
    assert params["operator_note"] == "operator replay required"


def test_claim_work_item_respects_next_retry_window(monkeypatch) -> None:
    """Claiming should not pick items whose next retry time is still in the future."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(claims_mod, "utc_now", _utc_now)

    queue.claim_work_item(
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    query, _params = cursor.execute.call_args.args
    assert "next_retry_at IS NULL" in query
    assert "next_retry_at <= %(now)s" in query
    assert "last_attempt_started_at = %(now)s" in query


def test_fail_work_item_records_retryable_failure_metadata(monkeypatch) -> None:
    """Retryable failures should preserve stage, class, and next-retry time."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(claims_mod, "utc_now", _utc_now)

    next_retry_at = datetime(2026, 4, 3, 12, 5, tzinfo=timezone.utc)
    queue.fail_work_item(
        work_item_id="work-1",
        error_message="boom",
        terminal=False,
        failure_stage="project_work_item",
        error_class="TimeoutError",
        failure_class=FailureClass.TIMEOUT,
        failure_code="projection_timeout",
        retry_disposition=FailureDisposition.RETRYABLE,
        next_retry_at=next_retry_at,
    )

    query, params = cursor.execute.call_args.args
    assert "failure_stage = %(failure_stage)s" in query
    assert "dead_lettered_at = %(dead_lettered_at)s" in query
    assert "next_retry_at = %(next_retry_at)s" in query
    assert "attempt_count =" not in query
    assert params["status"] == "pending"
    assert params["failure_class"] == FailureClass.TIMEOUT
    assert params["retry_disposition"] == FailureDisposition.RETRYABLE
    assert params["next_retry_at"] == next_retry_at
    assert params["dead_lettered_at"] is None


def test_fail_work_item_records_dead_letter_metadata(monkeypatch) -> None:
    """Terminal failures should set dead-letter metadata and clear retry timing."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(claims_mod, "utc_now", _utc_now)

    queue.fail_work_item(
        work_item_id="work-1",
        error_message="fatal",
        terminal=True,
        failure_stage="project_work_item",
        error_class="ValueError",
        failure_class=FailureClass.INPUT_INVALID,
        failure_code="invalid_fact_payload",
        retry_disposition=FailureDisposition.NON_RETRYABLE,
        operator_note="manual cleanup required",
    )

    _query, params = cursor.execute.call_args.args
    assert params["status"] == "failed"
    assert params["failure_class"] == FailureClass.INPUT_INVALID
    assert params["retry_disposition"] == FailureDisposition.NON_RETRYABLE
    assert params["dead_lettered_at"] == _utc_now()
    assert params["next_retry_at"] is None
    assert params["operator_note"] == "manual cleanup required"
