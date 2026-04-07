"""OpenAPI schema helpers for the FastAPI application factories."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .app_openapi_examples import (
    CODE_SEARCH_REQUEST_EXAMPLE as _CODE_SEARCH_REQUEST_EXAMPLE,
)
from .app_openapi_examples import REPOSITORY_STORY_EXAMPLE as _REPOSITORY_STORY_EXAMPLE
from .app_openapi_examples import (
    RESOLVE_ENTITY_RESPONSE_EXAMPLE as _RESOLVE_ENTITY_RESPONSE_EXAMPLE,
)
from .app_openapi_examples import SERVICE_CONTEXT_EXAMPLE as _SERVICE_CONTEXT_EXAMPLE
from .app_openapi_examples import SERVICE_STORY_EXAMPLE as _SERVICE_STORY_EXAMPLE
from .app_openapi_examples import WORKLOAD_CONTEXT_EXAMPLE as _WORKLOAD_CONTEXT_EXAMPLE
from .app_openapi_examples import WORKLOAD_STORY_EXAMPLE as _WORKLOAD_STORY_EXAMPLE
from .app_openapi_examples_investigation import (
    INVESTIGATION_RESPONSE_EXAMPLE as _INVESTIGATION_RESPONSE_EXAMPLE,
)


def build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Build and cache the OpenAPI schema for the HTTP API."""

    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    app.openapi_schema = _ensure_examples(schema)
    return app.openapi_schema


def _ensure_examples(schema: dict[str, Any]) -> dict[str, Any]:
    """Attach stable example payloads to the generated OpenAPI schema."""

    paths = schema.get("paths", {})

    def response_content(path: str, method: str) -> dict[str, Any]:
        """Return the JSON response content schema for a route/method pair."""

        return paths[path][method]["responses"]["200"]["content"]["application/json"]

    response_content("/api/v0/workloads/{workload_id}/context", "get")["examples"] = {
        "environment_context": {
            "summary": "Environment-scoped workload context",
            "value": _WORKLOAD_CONTEXT_EXAMPLE,
        }
    }
    response_content("/api/v0/services/{workload_id}/context", "get")["examples"] = {
        "service_alias": {
            "summary": "Service alias over the canonical workload model",
            "value": _SERVICE_CONTEXT_EXAMPLE,
        }
    }
    response_content("/api/v0/workloads/{workload_id}/story", "get")["examples"] = {
        "workload_story": {
            "summary": "Structured workload story",
            "value": _WORKLOAD_STORY_EXAMPLE,
        }
    }
    response_content("/api/v0/services/{workload_id}/story", "get")["examples"] = {
        "service_story": {
            "summary": "Structured service story",
            "value": _SERVICE_STORY_EXAMPLE,
        }
    }
    response_content("/api/v0/repositories/{repo_id}/story", "get")["examples"] = {
        "repository_story": {
            "summary": "Structured repository story",
            "value": _REPOSITORY_STORY_EXAMPLE,
        }
    }
    response_content(
        "/api/v0/investigations/services/{service_name}",
        "get",
    )["examples"] = {
        "service_investigation": {
            "summary": "Structured service investigation",
            "value": _INVESTIGATION_RESPONSE_EXAMPLE,
        }
    }
    response_content("/api/v0/entities/resolve", "post")["examples"] = {
        "workload_match": {
            "summary": "Resolve a workload by name",
            "value": _RESOLVE_ENTITY_RESPONSE_EXAMPLE,
        }
    }
    paths["/api/v0/code/search"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ] = {
        "code_only": {
            "summary": "Code-only search scoped to a canonical repository",
            "value": _CODE_SEARCH_REQUEST_EXAMPLE,
        }
    }
    return schema
