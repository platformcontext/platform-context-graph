"""HTTP routes for canonical workload context."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...domain.entities import EntityType
from ...domain.responses import WorkloadContextResponse
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_id_for_type,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/workloads", tags=["workloads"])


@router.get(
    "/{workload_id:path}/context",
    response_model=WorkloadContextResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_workload_context(
    workload_id: str,
    request: Request,
    environment: str | None = None,
    services: QueryServices = Depends(get_query_services),
):
    """Return context for a canonical workload.

    Args:
        workload_id: Canonical workload identifier.
        request: Incoming FastAPI request used for validation errors.
        environment: Optional environment scope.
        services: Query service container.

    Returns:
        Workload context or a problem response.
    """
    if not is_canonical_id_for_type(workload_id, EntityType.workload):
        return invalid_canonical_id_response(request, kind="workload")

    result = services.context.get_workload_context(
        services.database,
        workload_id=workload_id,
        environment=environment,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Workload not found"
        )
    return result
