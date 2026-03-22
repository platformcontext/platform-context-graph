"""HTTP routes for environment comparison queries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, Depends, Request

from ...domain.entities import EntityType
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_id_for_type,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/environments", tags=["environments"])


class CompareEnvironmentsRequest(BaseModel):
    """Request body for comparing workload environments."""

    model_config = ConfigDict(extra="forbid")

    workload_id: str
    left: str
    right: str


@router.post("/compare", responses=problem_detail_responses(400, 404))
def compare_environments(
    payload: CompareEnvironmentsRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Compare two environments for the same workload.

    Args:
        payload: Workload and environment pair to compare.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        The environment comparison result or a problem response.
    """
    if not is_canonical_id_for_type(payload.workload_id, EntityType.workload):
        return invalid_canonical_id_response(request, kind="workload")

    result = services.compare.compare_environments(
        services.database,
        workload_id=payload.workload_id,
        left=payload.left,
        right=payload.right,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Workload not found"
        )
    return result
