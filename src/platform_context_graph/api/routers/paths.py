"""HTTP routes for dependency-path explanations."""

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

router = APIRouter(prefix="/paths", tags=["paths"])


class ExplainDependencyPathRequest(BaseModel):
    """Request body for dependency-path explanation queries."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    environment: str | None = None


@router.post("/explain", responses=problem_detail_responses(400, 404))
def explain_dependency_path(
    payload: ExplainDependencyPathRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Explain a dependency path between two canonical entities.

    Args:
        payload: Source, target, and optional environment for the path query.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        The dependency path explanation or a problem response.
    """
    if not is_traversable_entity_id(payload.source):
        return invalid_canonical_id_response(request, kind="entity")
    if not is_traversable_entity_id(payload.target):
        return invalid_canonical_id_response(request, kind="entity")

    result = services.impact.explain_dependency_path(
        services.database,
        source=payload.source,
        target=payload.target,
        environment=payload.environment,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Path not found"
        )
    return result
