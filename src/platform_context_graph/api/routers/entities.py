"""HTTP routes for canonical entity resolution and context."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...domain.entities import EntityType
from ...domain.requests import ResolveEntityRequest
from ...domain.responses import EntityContextResponse, ResolveEntityResponse
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_entity_id,
    is_canonical_id_for_type,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/entities", tags=["entities"])


@router.post(
    "/resolve",
    response_model=ResolveEntityResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400),
)
def resolve_entity(
    payload: ResolveEntityRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Resolve a canonical entity from a user-supplied query.

    Args:
        payload: Entity resolution request body.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        Matching entities or a problem response when resolution fails.
    """
    if payload.repo_id is not None and not is_canonical_id_for_type(
        payload.repo_id, EntityType.repository
    ):
        return invalid_canonical_id_response(request, kind="repository")

    result = services.entity_resolution.resolve_entity(
        services.database,
        query=payload.query,
        types=payload.types,
        kinds=payload.kinds,
        environment=payload.environment,
        repo_id=payload.repo_id,
        exact=payload.exact,
        limit=payload.limit,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Entity resolution failed"
        )
    return result


@router.get(
    "/{entity_id:path}/context",
    response_model=EntityContextResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_entity_context(
    entity_id: str,
    request: Request,
    environment: str | None = None,
    services: QueryServices = Depends(get_query_services),
):
    """Return context for a canonical entity identifier.

    Args:
        entity_id: Canonical entity identifier.
        request: Incoming FastAPI request used for validation errors.
        environment: Optional environment scope.
        services: Query service container.

    Returns:
        Entity context or a problem response.
    """
    if not is_canonical_entity_id(entity_id):
        return invalid_canonical_id_response(request, kind="entity")

    result = services.context.get_entity_context(
        services.database,
        entity_id=entity_id,
        environment=environment,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Entity not found"
        )
    return result
