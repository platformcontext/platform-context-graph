"""Infrastructure-focused HTTP routes for the public API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, Request

from ..dependencies import QueryServices, get_query_services
from ._shared import (
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(tags=["infra"])

_DEFAULT_INFRA_TYPES = [
    "k8s_resource",
    "terraform_module",
    "terraform_resource",
    "cloud_resource",
]


class InfraSearchRequest(BaseModel):
    """Request body for infrastructure entity resolution."""

    model_config = ConfigDict(extra="forbid")

    query: str
    types: list[str] | None = None
    environment: str | None = None
    limit: int = Field(default=10, ge=1)


class InfraRelationshipsRequest(BaseModel):
    """Request body for infrastructure relationship lookups."""

    model_config = ConfigDict(extra="forbid")

    target: str
    relationship_type: str
    environment: str | None = None


@router.post("/infra/resources/search", responses=problem_detail_responses(400, 404))
def search_infra_resources(
    payload: InfraSearchRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Search infrastructure entities via the canonical entity-resolution path."""
    result = services.entity_resolution.resolve_entity(
        services.database,
        query=payload.query,
        types=payload.types or _DEFAULT_INFRA_TYPES,
        kinds=None,
        environment=payload.environment,
        repo_id=None,
        exact=False,
        limit=payload.limit,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Infrastructure search failed",
        )
    return result


@router.post("/infra/relationships", responses=problem_detail_responses(400, 404))
def infra_relationships(
    payload: InfraRelationshipsRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return relationship views for one infrastructure target."""
    result = services.infra.get_infra_relationships(
        services.database,
        target=payload.target,
        relationship_type=payload.relationship_type,
        environment=payload.environment,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Infrastructure relationship target not found",
        )
    return result


@router.get("/ecosystem/overview", responses=problem_detail_responses(400, 404))
def ecosystem_overview(
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return the current ecosystem overview snapshot."""
    result = services.infra.get_ecosystem_overview(services.database)
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Ecosystem overview unavailable",
        )
    return result
