"""HTTP routes for resource-to-code trace queries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, Request

from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_traversable_entity_id,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/traces", tags=["traces"])


class TraceResourceToCodeRequest(BaseModel):
    """Request body for tracing from a resource back to code."""

    model_config = ConfigDict(extra="forbid")

    start: str
    environment: str | None = None
    max_depth: int = Field(default=8, ge=1)


@router.post("/resource-to-code", responses=problem_detail_responses(400, 404))
def trace_resource_to_code(
    payload: TraceResourceToCodeRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Trace a canonical resource back to code and workload consumers.

    Args:
        payload: Trace parameters.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        Trace results or a problem response.
    """
    if not is_traversable_entity_id(payload.start):
        return invalid_canonical_id_response(request, kind="entity")

    result = services.impact.trace_resource_to_code(
        services.database,
        start=payload.start,
        environment=payload.environment,
        max_depth=payload.max_depth,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Trace source not found"
        )
    return result
