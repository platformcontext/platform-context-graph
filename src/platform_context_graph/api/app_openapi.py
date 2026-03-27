"""OpenAPI schema helpers for the FastAPI application factories."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

_WORKLOAD_CONTEXT_EXAMPLE = {
    "workload": {
        "id": "workload:payments-api",
        "type": "workload",
        "kind": "service",
        "name": "payments-api",
    },
    "instance": {
        "id": "workload-instance:payments-api:prod",
        "type": "workload_instance",
        "kind": "service",
        "name": "payments-api",
        "environment": "prod",
        "workload_id": "workload:payments-api",
    },
    "repositories": [
        {
            "id": "repository:r_ab12cd34",
            "type": "repository",
            "name": "payments-api",
            "repo_slug": "platformcontext/payments-api",
            "remote_url": "https://github.com/platformcontext/payments-api",
            "local_path": "/srv/repos/payments-api",
            "has_remote": True,
        }
    ],
    "images": [],
    "instances": [],
    "k8s_resources": [],
    "cloud_resources": [],
    "shared_resources": [],
    "dependencies": [],
    "entrypoints": [],
    "evidence": [],
}
_SERVICE_CONTEXT_EXAMPLE = {
    **_WORKLOAD_CONTEXT_EXAMPLE,
    "requested_as": "service",
}
_RESOLVE_ENTITY_RESPONSE_EXAMPLE = {
    "matches": [
        {
            "ref": _WORKLOAD_CONTEXT_EXAMPLE["workload"],
            "score": 0.98,
        }
    ]
}
_CODE_SEARCH_REQUEST_EXAMPLE = {
    "query": "process_payment",
    "repo_id": "repository:r_ab12cd34",
    "exact": False,
    "limit": 10,
}


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
