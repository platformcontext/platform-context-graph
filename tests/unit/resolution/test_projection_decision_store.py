"""Tests for the Phase 3 projection decision store."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.resolution.decisions.models import (
    ProjectionDecisionEvidenceRow,
)
from platform_context_graph.resolution.decisions.models import ProjectionDecisionRow
from platform_context_graph.resolution.decisions.postgres import (
    PostgresProjectionDecisionStore,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for decision-store tests."""

    return datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc)


def test_upsert_decision_persists_confidence_and_provenance(monkeypatch) -> None:
    """Upserting a decision should preserve confidence and provenance fields."""

    store = PostgresProjectionDecisionStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_decision(
        ProjectionDecisionRow(
            decision_id="decision-1",
            decision_type="project_workload",
            repository_id="repository:r_payments",
            source_run_id="run-123",
            work_item_id="work-1",
            subject="payments-service",
            confidence_score=0.9,
            confidence_reason="Direct workload fact corroborated by repository metadata",
            provenance_summary={"fact_ids": ["fact:repo", "fact:workload"]},
            created_at=_utc_now(),
        )
    )

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO projection_decisions" in query
    assert params["confidence_score"] == 0.9
    assert params["subject"] == "payments-service"


def test_insert_evidence_persists_fact_links(monkeypatch) -> None:
    """Evidence inserts should preserve fact linkage and evidence details."""

    store = PostgresProjectionDecisionStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.insert_evidence(
        [
            ProjectionDecisionEvidenceRow(
                evidence_id="evidence-1",
                decision_id="decision-1",
                fact_id="fact:workload",
                evidence_kind="direct",
                detail={"path": "deployments/payments.yaml"},
                created_at=_utc_now(),
            )
        ]
    )

    query, params = cursor.executemany.call_args.args
    assert "INSERT INTO projection_decision_evidence" in query
    assert params[0]["fact_id"] == "fact:workload"
    assert params[0]["evidence_kind"] == "direct"


def test_list_decisions_and_evidence_round_trip(monkeypatch) -> None:
    """Decision reads should reconstruct typed decision and evidence rows."""

    store = PostgresProjectionDecisionStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        [
            {
                "decision_id": "decision-1",
                "decision_type": "project_platform",
                "repository_id": "repository:r_payments",
                "source_run_id": "run-123",
                "work_item_id": "work-1",
                "subject": "payments-service",
                "confidence_score": 0.75,
                "confidence_reason": "Repository runtime implies platform edge",
                "provenance_summary": {"fact_ids": ["fact:repo"]},
                "created_at": _utc_now(),
            }
        ],
        [
            {
                "evidence_id": "evidence-1",
                "decision_id": "decision-1",
                "fact_id": "fact:repo",
                "evidence_kind": "inferred",
                "detail": {"source": "runtime"},
                "created_at": _utc_now(),
            }
        ],
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    decisions = store.list_decisions(
        repository_id="repository:r_payments",
        source_run_id="run-123",
    )
    evidence = store.list_evidence(decision_id="decision-1")

    assert decisions[0].decision_id == "decision-1"
    assert decisions[0].confidence_score == 0.75
    assert evidence[0].decision_id == "decision-1"
    assert evidence[0].evidence_kind == "inferred"
