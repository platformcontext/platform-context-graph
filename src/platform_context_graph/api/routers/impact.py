"""HTTP routes for change-surface impact queries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, Depends, Request

from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_traversable_entity_id,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/impact", tags=["impact"])


class ChangeSurfaceRequest(BaseModel):
    """Request body for change-surface analysis."""

    model_config = ConfigDict(extra="forbid")

    target: str
    environment: str | None = None


@router.post("/change-surface", responses=problem_detail_responses(400, 404))
def change_surface(
    payload: ChangeSurfaceRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return the change surface for a canonical entity.

    Args:
        payload: Change-surface query parameters.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        Impact analysis results or a problem response.
    """
    if not is_traversable_entity_id(payload.target):
        return invalid_canonical_id_response(request, kind="entity")

    result = services.impact.find_change_surface(
        services.database,
        target=payload.target,
        environment=payload.environment,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Change surface target not found",
        )
    return result
