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


class SkipRepositoryFactWorkItemsRequest(BaseModel):
    """Request body for intentionally skipping one repository's work items."""

    repository_id: str
    operator_note: str | None = None


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
        "work_item_id": getattr(row, "work_item_id", None),
        "work_type": getattr(row, "work_type", None),
        "repository_id": getattr(row, "repository_id", None),
        "source_run_id": getattr(row, "source_run_id", None),
        "lease_owner": getattr(row, "lease_owner", None),
        "status": getattr(row, "status", None),
        "attempt_count": getattr(row, "attempt_count", None),
        "last_error": getattr(row, "last_error", None),
        "failure_stage": getattr(row, "failure_stage", None),
        "error_class": getattr(row, "error_class", None),
        "failure_class": getattr(row, "failure_class", None),
        "failure_code": getattr(row, "failure_code", None),
        "retry_disposition": getattr(row, "retry_disposition", None),
        "dead_lettered_at": getattr(row, "dead_lettered_at", None),
        "last_attempt_started_at": getattr(row, "last_attempt_started_at", None),
        "last_attempt_finished_at": getattr(row, "last_attempt_finished_at", None),
        "next_retry_at": getattr(row, "next_retry_at", None),
        "operator_note": getattr(row, "operator_note", None),
        "parent_work_item_id": getattr(row, "parent_work_item_id", None),
        "projection_domain": getattr(row, "projection_domain", None),
        "accepted_generation_id": getattr(row, "accepted_generation_id", None),
        "authoritative_shared_domains": list(
            getattr(row, "authoritative_shared_domains", []) or []
        ),
        "completed_shared_domains": list(
            getattr(row, "completed_shared_domains", []) or []
        ),
        "shared_projection_pending": bool(
            getattr(row, "shared_projection_pending", False)
        ),
        "created_at": getattr(row, "created_at", None),
        "updated_at": getattr(row, "updated_at", None),
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


@router.post("/skip")
async def skip_repository_fact_work_items(
    payload: SkipRepositoryFactWorkItemsRequest,
) -> dict[str, Any]:
    """Mark one repository's actionable work items as intentionally skipped."""

    repository_id = payload.repository_id.strip()
    if not repository_id:
        raise HTTPException(
            status_code=400,
            detail="admin facts skip requires a non-empty repository_id",
        )
    queue = _require_fact_queue()
    rows = queue.skip_repository_work_items(
        repository_id=repository_id,
        operator_note=payload.operator_note,
    )
    info_logger(
        "Skipped repository fact work items through admin API",
        event_name="admin.facts.skipped",
        extra_keys={
            "count": len(rows),
            "repository_id": repository_id,
        },
    )
    get_observability().record_admin_fact_action(
        component="api",
        action="skip_repository_fact_work_items",
        outcome="success",
    )
    return {
        "count": len(rows),
        "items": [_serialize_work_item(row) for row in rows],
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
