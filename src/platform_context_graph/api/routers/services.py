"""HTTP routes exposing the service alias over canonical workloads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...domain.entities import EntityType
from ...domain.responses import WorkloadContextResponse
from ...query.context import ServiceAliasError
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_id_for_type,
    problem_detail_responses,
    problem_response,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/services", tags=["services"])


@router.get(
    "/{workload_id:path}/context",
    response_model=WorkloadContextResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_service_context(
    workload_id: str,
    request: Request,
    environment: str | None = None,
    services: QueryServices = Depends(get_query_services),
):
    """Return service-context data for a workload-id alias.

    Args:
        workload_id: Canonical workload identifier.
        request: Incoming FastAPI request used for validation errors.
        environment: Optional environment scope.
        services: Query service container.

    Returns:
        Service-context data or a problem response.
    """
    if not is_canonical_id_for_type(workload_id, EntityType.workload):
        return invalid_canonical_id_response(request, kind="service")

    try:
        result = services.context.get_service_context(
            services.database,
            workload_id=workload_id,
            environment=environment,
        )
    except ServiceAliasError as exc:
        return problem_response(
            request,
            title="Invalid service identifier",
            status_code=400,
            detail=str(exc),
        )

    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Service not found"
        )
    return result
