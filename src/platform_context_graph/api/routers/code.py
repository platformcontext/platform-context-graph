"""HTTP routes for code-oriented query operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, Request

from ...domain.entities import EntityType
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_id_for_type,
    problem_detail_responses,
    problem_response,
)

router = APIRouter(prefix="/code", tags=["code"])


class SearchCodeRequest(BaseModel):
    """Request body for code search."""

    model_config = ConfigDict(extra="forbid")

    query: str
    repo_id: str | None = None
    scope: str = "auto"
    exact: bool = False
    limit: int = Field(default=10, ge=0)
    edit_distance: int | None = Field(default=None, ge=0)


class CodeRelationshipsRequest(BaseModel):
    """Request body for code relationship lookups."""

    model_config = ConfigDict(extra="forbid")

    query_type: str
    target: str
    context: str | None = None
    repo_id: str | None = None
    scope: str = "auto"


class DeadCodeRequest(BaseModel):
    """Request body for dead-code analysis."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str | None = None
    scope: str = "auto"
    exclude_decorated_with: list[str] | None = None


class ComplexityRequest(BaseModel):
    """Request body for code complexity analysis."""

    model_config = ConfigDict(extra="forbid")

    mode: str = "top"
    limit: int = Field(default=10, ge=0)
    function_name: str | None = None
    path: str | None = None
    repo_id: str | None = None
    scope: str = "auto"


def _validate_repo_id(repo_id: str | None, request: Request):
    """Validate an optional canonical repository identifier.

    Args:
        repo_id: Canonical repository identifier, when provided.
        request: Incoming FastAPI request used to build problem responses.

    Returns:
        ``None`` when the repository identifier is valid, otherwise a problem
        response describing the validation failure.
    """
    if repo_id is not None and not is_canonical_id_for_type(
        repo_id, EntityType.repository
    ):
        return invalid_canonical_id_response(request, kind="repository")
    return None


@router.post("/search", responses=problem_detail_responses(400))
def search_code(
    payload: SearchCodeRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Search indexed code symbols and snippets.

    Args:
        payload: Search parameters.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        Search results or a problem response for invalid input.
    """
    invalid = _validate_repo_id(payload.repo_id, request)
    if invalid is not None:
        return invalid

    try:
        return services.code.search_code(
            services.database,
            query=payload.query,
            repo_id=payload.repo_id,
            scope=payload.scope,
            exact=payload.exact,
            limit=payload.limit,
            edit_distance=payload.edit_distance,
        )
    except ValueError as exc:
        return problem_response(
            request,
            title="Invalid code search request",
            status_code=400,
            detail=str(exc),
        )


@router.post("/relationships", responses=problem_detail_responses(400))
def code_relationships(
    payload: CodeRelationshipsRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Query relationship graphs for a code symbol.

    Args:
        payload: Relationship query parameters.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        Relationship results or a problem response for invalid input.
    """
    invalid = _validate_repo_id(payload.repo_id, request)
    if invalid is not None:
        return invalid

    try:
        return services.code.get_code_relationships(
            services.database,
            query_type=payload.query_type,
            target=payload.target,
            context=payload.context,
            repo_id=payload.repo_id,
            scope=payload.scope,
        )
    except ValueError as exc:
        return problem_response(
            request,
            title="Invalid code relationship request",
            status_code=400,
            detail=str(exc),
        )


@router.post("/dead-code", responses=problem_detail_responses(400))
def dead_code(
    payload: DeadCodeRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Run dead-code analysis across the indexed graph.

    Args:
        payload: Dead-code analysis parameters.
        services: Query service container.

    Returns:
        Dead-code analysis results or a problem response for invalid input.
    """
    invalid = _validate_repo_id(payload.repo_id, request)
    if invalid is not None:
        return invalid

    try:
        return services.code.find_dead_code(
            services.database,
            repo_id=payload.repo_id,
            scope=payload.scope,
            exclude_decorated_with=payload.exclude_decorated_with,
        )
    except ValueError as exc:
        return problem_response(
            request,
            title="Invalid dead-code request",
            status_code=400,
            detail=str(exc),
        )


@router.post("/complexity", responses=problem_detail_responses(400))
def complexity(
    payload: ComplexityRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Run code-complexity analysis for the indexed graph.

    Args:
        payload: Complexity query parameters.
        request: Incoming FastAPI request used for validation errors.
        services: Query service container.

    Returns:
        Complexity analysis results or a problem response when the request is
        invalid.
    """
    invalid = _validate_repo_id(payload.repo_id, request)
    if invalid is not None:
        return invalid

    try:
        return services.code.get_complexity(
            services.database,
            mode=payload.mode,
            limit=payload.limit,
            function_name=payload.function_name,
            path=payload.path,
            repo_id=payload.repo_id,
            scope=payload.scope,
        )
    except ValueError as exc:
        return problem_response(
            request,
            title="Invalid complexity request",
            status_code=400,
            detail=str(exc),
        )
