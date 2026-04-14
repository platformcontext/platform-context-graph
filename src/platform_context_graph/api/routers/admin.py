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
    """Shared-write tuning is now served by the Go admin surface."""
    raise HTTPException(
        status_code=410,
        detail="Shared-projection tuning report has migrated to the Go admin surface.",
    )


@router.post("/reindex")
async def reindex(
    payload: ReindexRequest | None = None,
    database: Any = Depends(get_database),
) -> dict[str, Any]:
    """Reindex endpoint has migrated to the Go admin surface."""
    raise HTTPException(
        status_code=410,
        detail="Admin reindex has migrated to the Go admin surface at /admin/reindex.",
    )
