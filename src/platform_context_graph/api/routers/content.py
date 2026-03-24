"""HTTP routes for content retrieval and indexed source search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ...domain.entities import EntityType
from ...domain.responses import (
    EntityContentResponse,
    EntityContentSearchResponse,
    FileContentResponse,
    FileContentSearchResponse,
    FileLinesResponse,
)
from ..dependencies import QueryServices, get_query_services
from ._shared import (
    invalid_canonical_id_response,
    is_canonical_content_entity_id,
    is_canonical_id_for_type,
    problem_detail_responses,
    service_error_response,
    service_result_has_error,
)

router = APIRouter(prefix="/content", tags=["content"])


class FileContentRequest(BaseModel):
    """Request body for portable file-content retrieval."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    relative_path: str


class FileLinesRequest(BaseModel):
    """Request body for portable file line-range retrieval."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    relative_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class EntityContentRequest(BaseModel):
    """Request body for entity-content retrieval."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str


class FileContentSearchRequest(BaseModel):
    """Request body for file-content search."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    repo_ids: list[str] | None = None
    languages: list[str] | None = None
    artifact_types: list[str] | None = None
    template_dialects: list[str] | None = None
    iac_relevant: bool | None = None


class EntityContentSearchRequest(BaseModel):
    """Request body for entity-content search."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    entity_types: list[str] | None = None
    repo_ids: list[str] | None = None
    languages: list[str] | None = None
    artifact_types: list[str] | None = None
    template_dialects: list[str] | None = None
    iac_relevant: bool | None = None


@router.post(
    "/files/read",
    response_model=FileContentResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_file_content(
    payload: FileContentRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return one file's content using portable repo-relative addressing."""

    if not is_canonical_id_for_type(payload.repo_id, EntityType.repository):
        return invalid_canonical_id_response(request, kind="repository")
    result = services.content.get_file_content(
        services.database,
        repo_id=payload.repo_id,
        relative_path=payload.relative_path,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="File content unavailable",
        )
    return result


@router.post(
    "/files/lines",
    response_model=FileLinesResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_file_lines(
    payload: FileLinesRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return one line range for a repo-relative file."""

    if not is_canonical_id_for_type(payload.repo_id, EntityType.repository):
        return invalid_canonical_id_response(request, kind="repository")
    result = services.content.get_file_lines(
        services.database,
        repo_id=payload.repo_id,
        relative_path=payload.relative_path,
        start_line=payload.start_line,
        end_line=payload.end_line,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="File content unavailable",
        )
    return result


@router.post(
    "/entities/read",
    response_model=EntityContentResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def get_entity_content(
    payload: EntityContentRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Return source for one content-bearing graph entity."""

    if not is_canonical_content_entity_id(payload.entity_id):
        return invalid_canonical_id_response(request, kind="content entity")
    result = services.content.get_entity_content(
        services.database,
        entity_id=payload.entity_id,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Entity content unavailable",
        )
    return result


@router.post(
    "/files/search",
    response_model=FileContentSearchResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def search_file_content(
    payload: FileContentSearchRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Search indexed file content using portable repository identifiers."""

    if payload.repo_ids:
        for repo_id in payload.repo_ids:
            if not is_canonical_id_for_type(repo_id, EntityType.repository):
                return invalid_canonical_id_response(request, kind="repository")
    result = services.content.search_file_content(
        services.database,
        pattern=payload.pattern,
        repo_ids=payload.repo_ids,
        languages=payload.languages,
        artifact_types=payload.artifact_types,
        template_dialects=payload.template_dialects,
        iac_relevant=payload.iac_relevant,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="File content search unavailable",
        )
    return result


@router.post(
    "/entities/search",
    response_model=EntityContentSearchResponse,
    response_model_exclude_none=True,
    responses=problem_detail_responses(400, 404),
)
def search_entity_content(
    payload: EntityContentSearchRequest,
    request: Request,
    services: QueryServices = Depends(get_query_services),
):
    """Search indexed entity snippets using portable identifiers."""

    if payload.repo_ids:
        for repo_id in payload.repo_ids:
            if not is_canonical_id_for_type(repo_id, EntityType.repository):
                return invalid_canonical_id_response(request, kind="repository")
    result = services.content.search_entity_content(
        services.database,
        pattern=payload.pattern,
        entity_types=payload.entity_types,
        repo_ids=payload.repo_ids,
        languages=payload.languages,
        artifact_types=payload.artifact_types,
        template_dialects=payload.template_dialects,
        iac_relevant=payload.iac_relevant,
    )
    if service_result_has_error(result):
        return service_error_response(
            request,
            detail=result["error"],
            not_found_title="Entity content search unavailable",
        )
    return result
