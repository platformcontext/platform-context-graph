"""Administrative API endpoints for graph maintenance operations.

Recovery operations (refinalize, replay) are owned by the Go ingester admin
surface at /admin/refinalize and /admin/replay. This module retains only the
reindex and tuning report endpoints that have not yet been ported.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import get_database
from ...query.status import request_ingester_reindex_control
from ...query.shared_projection_tuning import build_tuning_report

router = APIRouter(prefix="/admin", tags=["admin"])


class ReindexRequest(BaseModel):
    """Request body for the admin reindex endpoint."""

    ingester: str = "repository"
    scope: str = "workspace"
    force: bool = True


@router.get("/shared-projection/tuning-report")
async def shared_projection_tuning_report(
    include_platform: bool = False,
) -> dict[str, Any]:
    """Return the deterministic shared-write tuning report payload."""

    return build_tuning_report(include_platform=include_platform)


@router.post("/reindex")
async def reindex(
    payload: ReindexRequest | None = None,
    database: Any = Depends(get_database),
) -> dict[str, Any]:
    """Persist a full reindex request for the ingester to claim asynchronously."""

    payload = payload or ReindexRequest()
    normalized_ingester = str(payload.ingester or "repository").strip().lower()
    normalized_scope = str(payload.scope or "workspace").strip().lower()
    if normalized_ingester != "repository":
        raise HTTPException(
            status_code=404,
            detail=f"Unknown ingester for admin reindex: {payload.ingester}",
        )
    if normalized_scope != "workspace":
        raise HTTPException(
            status_code=400,
            detail="Admin reindex currently supports only scope='workspace'.",
        )

    result = request_ingester_reindex_control(
        database,
        ingester=normalized_ingester,
        requested_by="api",
        force=bool(payload.force),
        scope=normalized_scope,
    )
    return {
        "status": "accepted" if result.get("accepted", True) else "unavailable",
        "ingester": normalized_ingester,
        "request_token": result.get("reindex_request_token"),
        "request_state": result.get("reindex_request_state"),
        "requested_at": result.get("reindex_requested_at"),
        "requested_by": result.get("reindex_requested_by"),
        "force": bool(result.get("requested_force", payload.force)),
        "scope": result.get("requested_scope") or normalized_scope,
        "run_id": result.get("run_id"),
    }
