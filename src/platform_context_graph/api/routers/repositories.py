"""Repository-focused HTTP routes for the public API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...domain.entities import EntityType
from ...domain.responses import StoryResponse
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_id_for_type,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", responses=problem_detail_responses(400, 404))
def list_repositories(
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """List repositories currently known to the graph."""
    result = services.repositories.list_repositories(services.database)
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Repositories unavailable"
        )
    return result


@router.get("/{repo_id:path}/context", responses=problem_detail_responses(400, 404))
def get_repository_context(
    repo_id: str,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return detailed context for a canonical repository identifier."""
    if not is_canonical_id_for_type(repo_id, EntityType.repository):
        return invalid_canonical_id_response(request, kind="repository")

    result = services.repositories.get_repository_context(
        services.database,
        repo_id=repo_id,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Repository not found"
        )
    return result


@router.get(
    "/{repo_id:path}/story",
    response_model=StoryResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_repository_story(
    repo_id: str,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return a structured story for a canonical repository identifier."""

    if not is_canonical_id_for_type(repo_id, EntityType.repository):
        return invalid_canonical_id_response(request, kind="repository")

    result = services.repositories.get_repository_story(
        services.database,
        repo_id=repo_id,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Repository not found"
        )
    return result


@router.get("/{repo_id:path}/stats", responses=problem_detail_responses(400, 404))
def get_repository_stats(
    repo_id: str,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return summary statistics for a canonical repository identifier."""
    if not is_canonical_id_for_type(repo_id, EntityType.repository):
        return invalid_canonical_id_response(request, kind="repository")

    result = services.repositories.get_repository_stats(
        services.database,
        repo_id=repo_id,
    )
    if service_result_has_error(result):
        return service_error_response(
            request, detail=result["error"], not_found_title="Repository not found"
        )
    return result


@router.get("/{repo_id:path}/coverage", responses=problem_detail_responses(400, 404))
def get_repository_coverage(
    repo_id: str,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return durable coverage for a canonical repository identifier."""
    if not is_canonical_id_for_type(repo_id, EntityType.repository):
        return invalid_canonical_id_response(request, kind="repository")

    result = services.repositories.get_repository_coverage(
        services.database,
        repo_id=repo_id,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Repository coverage not found",
        )
    return result
