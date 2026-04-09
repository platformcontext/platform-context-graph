"""Tests for the facts-first admin inspection router."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from platform_context_graph.api.routers import admin_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for admin facts router tests."""

    return datetime(2026, 4, 3, 17, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_list_fact_work_items_returns_failure_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin facts list endpoint should return durable work-item fields."""

    class _FakeQueue:
        enabled = True

        def list_work_items(self, **kwargs):
            assert kwargs == {
                "statuses": ["failed"],
                "repository_id": "repository:r_payments",
                "source_run_id": None,
                "work_type": None,
                "failure_class": "timeout",
                "limit": 25,
            }
            return [
                SimpleNamespace(
                    work_item_id="work-1",
                    work_type="project-git-facts",
                    repository_id="repository:r_payments",
                    source_run_id="run-123",
                    lease_owner="indexing",
                    status="failed",
                    attempt_count=3,
                    last_error="boom",
                    failure_stage="project_work_item",
                    error_class="TimeoutError",
                    failure_class="timeout",
                    failure_code="timeout_error",
                    retry_disposition="retryable",
                    dead_lettered_at=_utc_now(),
                    last_attempt_started_at=_utc_now(),
                    last_attempt_finished_at=_utc_now(),
                    next_retry_at=None,
                    operator_note="watching this one",
                    created_at=_utc_now(),
                    updated_at=_utc_now(),
                )
            ]

    monkeypatch.setattr(admin_facts, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin_facts.list_fact_work_items(
        admin_facts.ListFactWorkItemsRequest(
            statuses=["failed"],
            repository_id="repository:r_payments",
            failure_class="timeout",
            limit=25,
        )
    )

    assert response["count"] == 1
    assert response["items"][0]["failure_class"] == "timeout"
    assert response["items"][0]["lease_owner"] == "indexing"
    assert response["items"][0]["operator_note"] == "watching this one"


@pytest.mark.asyncio
async def test_list_projection_decisions_returns_optional_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin decision endpoint should return decisions and optional evidence."""

    class _FakeStore:
        enabled = True

        def list_decisions(self, **kwargs):
            assert kwargs == {
                "repository_id": "repository:r_payments",
                "source_run_id": "run-123",
                "decision_type": "project_workloads",
                "limit": 10,
            }
            return [
                SimpleNamespace(
                    decision_id="decision-1",
                    decision_type="project_workloads",
                    repository_id="repository:r_payments",
                    source_run_id="run-123",
                    work_item_id="work-1",
                    subject="repository:r_payments",
                    confidence_score=0.9,
                    confidence_reason="Strong workload evidence",
                    provenance_summary={"fact_count": 2},
                    created_at=_utc_now(),
                )
            ]

        def list_evidence(self, *, decision_id: str):
            assert decision_id == "decision-1"
            return [
                SimpleNamespace(
                    evidence_id="evidence-1",
                    decision_id="decision-1",
                    fact_id="fact:workload",
                    evidence_kind="input",
                    detail={"fact_type": "WorkloadInputObserved"},
                    created_at=_utc_now(),
                )
            ]

    monkeypatch.setattr(
        admin_facts,
        "get_projection_decision_store",
        lambda: _FakeStore(),
    )

    response = await admin_facts.list_projection_decisions(
        admin_facts.ListProjectionDecisionsRequest(
            repository_id="repository:r_payments",
            source_run_id="run-123",
            decision_type="project_workloads",
            include_evidence=True,
            limit=10,
        )
    )

    assert response["count"] == 1
    assert response["decisions"][0]["decision_type"] == "project_workloads"
    assert response["decisions"][0]["evidence"][0]["fact_id"] == "fact:workload"


@pytest.mark.asyncio
async def test_list_fact_work_items_rejects_missing_queue() -> None:
    """The admin facts list endpoint should fail when the queue is unavailable."""

    with pytest.raises(HTTPException) as exc_info:
        await admin_facts.list_fact_work_items(
            admin_facts.ListFactWorkItemsRequest(statuses=["failed"])
        )

    assert exc_info.value.status_code == 503
