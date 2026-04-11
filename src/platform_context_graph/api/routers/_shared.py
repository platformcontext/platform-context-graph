"""Shared helpers for FastAPI router validation and problem responses."""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from ...domain.entities import EntityType
from ...domain.responses import ProblemDetails
from ...content.identity import is_content_entity_id

_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[^/\s:][^/\s]*(?::[^/\s:][^/\s]*)*$")
_KNOWN_CANONICAL_PREFIXES = frozenset(
    entity_type.value.replace("_", "-") for entity_type in EntityType
)
_TRAVERSABLE_CANONICAL_PREFIXES = _KNOWN_CANONICAL_PREFIXES
_NOT_FOUND_MARKERS = (
    "not found",
    "has no instance for environment",
)
_PROBLEM_SCHEMA = ProblemDetails.model_json_schema()


def _canonical_prefix(entity_type: EntityType) -> str:
    """Return the canonical identifier prefix for an entity type."""
    return entity_type.value.replace("_", "-")


def is_canonical_entity_id(value: str) -> bool:
    """Return whether a string is any valid canonical entity identifier."""
    if value.startswith("/") or not _CANONICAL_ID_RE.match(value):
        return False
    prefix, _, _ = value.partition(":")
    return prefix in _KNOWN_CANONICAL_PREFIXES


def is_traversable_entity_id(value: str) -> bool:
    """Return whether a canonical entity identifier can participate in graph traversal."""
    if value.startswith("/") or not _CANONICAL_ID_RE.match(value):
        return False
    prefix, _, _ = value.partition(":")
    return prefix in _TRAVERSABLE_CANONICAL_PREFIXES


def is_canonical_id_for_type(value: str, entity_type: EntityType) -> bool:
    """Return whether a canonical identifier matches a specific entity type."""
    if not is_canonical_entity_id(value):
        return False
    prefix, _, _ = value.partition(":")
    return prefix == _canonical_prefix(entity_type)


def is_canonical_content_entity_id(value: str) -> bool:
    """Return whether a string is a valid content-entity identifier."""

    return is_content_entity_id(value)


def problem_detail_responses(
    *status_codes: int,
) -> dict[int | str, dict[str, Any]]:
    """Build FastAPI response metadata for RFC 7807 problem payloads."""
    responses: dict[int, dict[str, Any]] = {}
    for status_code in status_codes:
        responses[status_code] = {
            "description": f"Problem details response ({status_code})",
            "content": {
                "application/problem+json": {
                    "schema": _PROBLEM_SCHEMA,
                }
            },
        }
    return responses


def problem_response(
    request: Request,
    *,
    title: str,
    status_code: int,
    detail: str | None = None,
    problem_type: str = "about:blank",
) -> JSONResponse:
    """Create a JSON problem-details response for an HTTP request."""
    problem = ProblemDetails(
        type=problem_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
    )


def invalid_canonical_id_response(
    request: Request,
    *,
    kind: str,
) -> JSONResponse:
    """Return a standardized invalid-canonical-ID problem response."""
    return problem_response(
        request,
        title=f"Invalid canonical {kind} identifier",
        status_code=400,
        detail=(
            f"Expected a canonical {kind} identifier. "
            "Use POST /api/v0/entities/resolve for fuzzy names, aliases, and raw paths."
        ),
    )


def service_error_response(
    request: Request,
    *,
    detail: str,
    not_found_title: str,
) -> JSONResponse:
    """Translate a service-layer error string into a problem-details response."""
    detail_lower = detail.lower()
    status_code = (
        404 if any(marker in detail_lower for marker in _NOT_FOUND_MARKERS) else 400
    )
    title = not_found_title if status_code == 404 else "Invalid request"
    return problem_response(
        request,
        title=title,
        status_code=status_code,
        detail=detail,
    )


def not_implemented_response(request: Request, *, detail: str) -> JSONResponse:
    """Return a standardized 501 response for unsupported operations."""
    return problem_response(
        request,
        title="Not implemented",
        status_code=501,
        detail=detail,
    )


def service_result_has_error(result: Any) -> bool:
    """Return whether a service-layer result is an error mapping."""
    return (
        isinstance(result, dict)
        and isinstance(result.get("error"), str)
        and ("success" not in result or result.get("success") is False)
    )
