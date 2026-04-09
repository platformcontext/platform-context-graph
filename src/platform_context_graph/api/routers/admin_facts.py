"""Administrative facts-first inspection endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel

from ...facts.state import get_fact_work_queue
from ...facts.state import get_projection_decision_store
from ...observability import get_observability
from ...utils.debug_log import info_logger

router = APIRouter(prefix="/admin/facts", tags=["admin"])


class ListFactWorkItemsRequest(BaseModel):
    """Request body for listing fact work items."""

    statuses: list[str] | None = None
    repository_id: str | None = None
    source_run_id: str | None = None
    work_type: str | None = None
    failure_class: str | None = None
    limit: int = 100


class ListProjectionDecisionsRequest(BaseModel):
    """Request body for listing projection decisions."""

    repository_id: str
    source_run_id: str
    decision_type: str | None = None
    include_evidence: bool = False
    limit: int = 100


class DeadLetterFactWorkItemsRequest(BaseModel):
    """Request body for manually dead-lettering selected fact work items."""

    work_item_ids: list[str] | None = None
    repository_id: str | None = None
    source_run_id: str | None = None
    work_type: str | None = None
    failure_class: str = "manual_override"
    operator_note: str | None = None
    limit: int = 100


class RequestFactBackfillRequest(BaseModel):
    """Request body for creating a durable fact backfill request."""

    repository_id: str | None = None
    source_run_id: str | None = None
    operator_note: str | None = None


class ListFactReplayEventsRequest(BaseModel):
    """Request body for listing durable replay-event audit rows."""

    repository_id: str | None = None
    source_run_id: str | None = None
    work_item_id: str | None = None
    failure_class: str | None = None
    limit: int = 100


class ReplayFailedFactsRequest(BaseModel):
    """Request body for replaying terminal fact work items."""

    work_item_ids: list[str] | None = None
    repository_id: str | None = None
    source_run_id: str | None = None
    work_type: str | None = None
    failure_class: str | None = None
    operator_note: str | None = None
    limit: int = 100


def _require_fact_queue() -> Any:
    """Return the configured fact queue or raise an HTTP 503."""

    queue = get_fact_work_queue()
    if queue is None or not getattr(queue, "enabled", True):
        raise HTTPException(
            status_code=503,
            detail="facts-first work queue is not configured",
        )
    return queue


def _serialize_work_item(row: Any) -> dict[str, Any]:
    """Return one admin-friendly work-item payload."""

    return {
        "work_item_id": row.work_item_id,
        "work_type": row.work_type,
        "repository_id": row.repository_id,
        "source_run_id": row.source_run_id,
        "lease_owner": row.lease_owner,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "last_error": row.last_error,
        "failure_stage": row.failure_stage,
        "error_class": row.error_class,
        "failure_class": row.failure_class,
        "failure_code": row.failure_code,
        "retry_disposition": row.retry_disposition,
        "dead_lettered_at": row.dead_lettered_at,
        "last_attempt_started_at": row.last_attempt_started_at,
        "last_attempt_finished_at": row.last_attempt_finished_at,
        "next_retry_at": row.next_retry_at,
        "operator_note": row.operator_note,
        "parent_work_item_id": row.parent_work_item_id,
        "projection_domain": row.projection_domain,
        "accepted_generation_id": row.accepted_generation_id,
        "authoritative_shared_domains": row.authoritative_shared_domains,
        "completed_shared_domains": row.completed_shared_domains,
        "shared_projection_pending": row.shared_projection_pending,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.post("/work-items/query")
async def list_fact_work_items(
    payload: ListFactWorkItemsRequest,
) -> dict[str, Any]:
    """List fact work items with durable failure metadata."""

    queue = _require_fact_queue()
    rows = queue.list_work_items(
        statuses=payload.statuses,
        repository_id=payload.repository_id,
        source_run_id=payload.source_run_id,
        work_type=payload.work_type,
        failure_class=payload.failure_class,
        limit=max(payload.limit, 1),
    )
    info_logger(
        "Listed fact work items through admin API",
        event_name="admin.facts.work_items.listed",
        extra_keys={
            "count": len(rows),
            "statuses": payload.statuses,
            "repository_id": payload.repository_id,
            "source_run_id": payload.source_run_id,
            "work_type": payload.work_type,
            "failure_class": payload.failure_class,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="list_fact_work_items",
        outcome="success",
    )
    return {
        "count": len(rows),
        "items": [_serialize_work_item(row) for row in rows],
    }


@router.post("/decisions/query")
async def list_projection_decisions(
    payload: ListProjectionDecisionsRequest,
) -> dict[str, Any]:
    """List projection decisions and optional evidence for one repo/run pair."""

    store = get_projection_decision_store()
    if store is None or not getattr(store, "enabled", True):
        raise HTTPException(
            status_code=503,
            detail="projection decision store is not configured",
        )
    decisions = store.list_decisions(
        repository_id=payload.repository_id,
        source_run_id=payload.source_run_id,
        decision_type=payload.decision_type,
        limit=max(payload.limit, 1),
    )
    evidence_by_decision: dict[str, list[dict[str, Any]]] = {}
    if payload.include_evidence:
        for decision in decisions:
            evidence_rows = store.list_evidence(decision_id=decision.decision_id)
            evidence_by_decision[decision.decision_id] = [
                {
                    "evidence_id": row.evidence_id,
                    "decision_id": row.decision_id,
                    "fact_id": row.fact_id,
                    "evidence_kind": row.evidence_kind,
                    "detail": row.detail,
                    "created_at": row.created_at,
                }
                for row in evidence_rows
            ]
    info_logger(
        "Listed projection decisions through admin API",
        event_name="admin.facts.decisions.listed",
        extra_keys={
            "count": len(decisions),
            "repository_id": payload.repository_id,
            "source_run_id": payload.source_run_id,
            "decision_type": payload.decision_type,
            "include_evidence": payload.include_evidence,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="list_projection_decisions",
        outcome="success",
    )
    return {
        "count": len(decisions),
        "decisions": [
            {
                "decision_id": row.decision_id,
                "decision_type": row.decision_type,
                "repository_id": row.repository_id,
                "source_run_id": row.source_run_id,
                "work_item_id": row.work_item_id,
                "subject": row.subject,
                "confidence_score": row.confidence_score,
                "confidence_reason": row.confidence_reason,
                "provenance_summary": row.provenance_summary,
                "created_at": row.created_at,
                "evidence": evidence_by_decision.get(row.decision_id),
            }
            for row in decisions
        ],
    }


@router.post("/dead-letter")
async def dead_letter_fact_work_items(
    payload: DeadLetterFactWorkItemsRequest,
) -> dict[str, Any]:
    """Move selected work items into durable dead-letter state."""

    if not any(
        (
            payload.work_item_ids,
            payload.repository_id,
            payload.source_run_id,
            payload.work_type,
        )
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one selector is required: work_item_ids, repository_id, "
                "source_run_id, or work_type."
            ),
        )
    queue = _require_fact_queue()
    rows = queue.dead_letter_work_items(
        work_item_ids=payload.work_item_ids,
        repository_id=payload.repository_id,
        source_run_id=payload.source_run_id,
        work_type=payload.work_type,
        failure_class=payload.failure_class,
        operator_note=payload.operator_note,
        limit=max(payload.limit, 1),
    )
    info_logger(
        "Dead-lettered fact work items through admin API",
        event_name="admin.facts.dead_lettered",
        extra_keys={
            "count": len(rows),
            "repository_id": payload.repository_id,
            "source_run_id": payload.source_run_id,
            "work_type": payload.work_type,
            "failure_class": payload.failure_class,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="dead_letter_fact_work_items",
        outcome="success",
    )
    return {
        "count": len(rows),
        "items": [_serialize_work_item(row) for row in rows],
    }


@router.post("/replay")
async def replay_failed_facts(
    payload: ReplayFailedFactsRequest,
) -> dict[str, Any]:
    """Replay terminally failed fact-projection work items."""

    if not any(
        (
            payload.work_item_ids,
            payload.repository_id,
            payload.source_run_id,
            payload.work_type,
            payload.failure_class,
        )
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "admin facts replay requires at least one selector: "
                "work_item_ids, repository_id, source_run_id, work_type, "
                "or failure_class"
            ),
        )
    queue = _require_fact_queue()
    replayed = queue.replay_failed_work_items(
        work_item_ids=payload.work_item_ids,
        repository_id=payload.repository_id,
        source_run_id=payload.source_run_id,
        work_type=payload.work_type,
        failure_class=payload.failure_class,
        operator_note=payload.operator_note,
        limit=max(payload.limit, 1),
    )
    info_logger(
        "Replayed terminal fact work items",
        event_name="admin.facts.replayed",
        extra_keys={
            "replayed_count": len(replayed),
            "work_item_ids": [row.work_item_id for row in replayed],
            "repository_id": payload.repository_id,
            "source_run_id": payload.source_run_id,
            "work_type": payload.work_type,
            "failure_class": payload.failure_class,
            "operator_note": payload.operator_note,
            "limit": payload.limit,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="replay_failed_work_items",
        outcome="success",
    )
    return {
        "status": "replayed",
        "replayed_count": len(replayed),
        "work_item_ids": [row.work_item_id for row in replayed],
        "replayed": [
            {
                "work_item_id": row.work_item_id,
                "repository_id": row.repository_id,
                "source_run_id": row.source_run_id,
                "work_type": row.work_type,
                "failure_class": row.failure_class,
            }
            for row in replayed
        ],
    }


@router.post("/backfill")
async def request_fact_backfill(
    payload: RequestFactBackfillRequest,
) -> dict[str, Any]:
    """Create one durable operator backfill request."""

    if not any((payload.repository_id, payload.source_run_id)):
        raise HTTPException(
            status_code=400,
            detail="At least one selector is required: repository_id or source_run_id.",
        )
    queue = _require_fact_queue()
    row = queue.request_backfill(
        repository_id=payload.repository_id,
        source_run_id=payload.source_run_id,
        operator_note=payload.operator_note,
    )
    info_logger(
        "Created fact backfill request through admin API",
        event_name="admin.facts.backfill.requested",
        extra_keys={
            "backfill_request_id": row.backfill_request_id,
            "repository_id": row.repository_id,
            "source_run_id": row.source_run_id,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="request_fact_backfill",
        outcome="success",
    )
    return {
        "status": "accepted",
        "backfill_request": {
            "backfill_request_id": row.backfill_request_id,
            "repository_id": row.repository_id,
            "source_run_id": row.source_run_id,
            "operator_note": row.operator_note,
            "created_at": row.created_at,
        },
    }


@router.post("/replay-events/query")
async def list_fact_replay_events(
    payload: ListFactReplayEventsRequest,
) -> dict[str, Any]:
    """List durable replay-event audit rows."""

    queue = _require_fact_queue()
    rows = queue.list_replay_events(
        repository_id=payload.repository_id,
        source_run_id=payload.source_run_id,
        work_item_id=payload.work_item_id,
        failure_class=payload.failure_class,
        limit=max(payload.limit, 1),
    )
    info_logger(
        "Listed fact replay events through admin API",
        event_name="admin.facts.replay_events.listed",
        extra_keys={
            "count": len(rows),
            "repository_id": payload.repository_id,
            "source_run_id": payload.source_run_id,
            "work_item_id": payload.work_item_id,
            "failure_class": payload.failure_class,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="list_fact_replay_events",
        outcome="success",
    )
    return {
        "count": len(rows),
        "events": [
            {
                "replay_event_id": row.replay_event_id,
                "work_item_id": row.work_item_id,
                "repository_id": row.repository_id,
                "source_run_id": row.source_run_id,
                "work_type": row.work_type,
                "failure_class": row.failure_class,
                "operator_note": row.operator_note,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }
