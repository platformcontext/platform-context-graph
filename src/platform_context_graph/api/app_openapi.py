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
_WORKLOAD_STORY_EXAMPLE = {
    "subject": _WORKLOAD_CONTEXT_EXAMPLE["workload"],
    "story": [
        "payments-api has an environment-scoped instance for prod.",
        "Owned by repositories payments-api.",
    ],
    "story_sections": [
        {
            "id": "runtime",
            "title": "Runtime",
            "summary": "Selected instance workload-instance:payments-api:prod.",
            "items": [_WORKLOAD_CONTEXT_EXAMPLE["instance"]],
        }
    ],
    "deployment_overview": {
        "instances": [_WORKLOAD_CONTEXT_EXAMPLE["instance"]],
        "repositories": _WORKLOAD_CONTEXT_EXAMPLE["repositories"],
        "entrypoints": [],
        "cloud_resources": [],
        "shared_resources": [],
        "dependencies": [],
    },
    "evidence": [],
    "limitations": [],
    "coverage": None,
    "drilldowns": {
        "workload_context": {"workload_id": "workload:payments-api"},
        "service_context": {"workload_id": "workload:payments-api"},
    },
}
_SERVICE_STORY_EXAMPLE = {
    **_WORKLOAD_STORY_EXAMPLE,
    "requested_as": "service",
}
_REPOSITORY_STORY_EXAMPLE = {
    "subject": {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-api",
    },
    "story": [
        "Public entrypoints: payments-api.prod.example.com.",
        "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
    ],
    "story_sections": [
        {
            "id": "deployment",
            "title": "Deployment",
            "summary": "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
            "items": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
        }
    ],
    "deployment_overview": {
        "internet_entrypoints": ["payments-api.prod.example.com"],
        "internal_entrypoints": [],
        "api_surface": {"docs_routes": ["/_specs"], "api_versions": ["v1"]},
        "runtime_platforms": [{"kind": "eks"}],
        "delivery_paths": [
            {
                "path_kind": "gitops",
                "controller": "github_actions",
                "delivery_mode": "eks_gitops",
                "deployment_sources": ["helm-charts"],
                "platform_kinds": ["eks"],
            }
        ],
        "controller_driven_paths": [],
        "consumer_repositories": [],
        "deployment_story": [
            "Public entrypoints: payments-api.prod.example.com.",
            "API surface exposes versions v1 and docs /_specs.",
            "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
        ],
        "topology_story": [
            "Public entrypoints: payments-api.prod.example.com.",
            "API surface exposes versions v1 and docs /_specs.",
            "Deployment flows through github_actions eks_gitops from helm-charts onto eks.",
        ],
    },
    "code_overview": {
        "file_count": 42,
        "functions": 12,
        "classes": 3,
        "class_methods": 4,
    },
    "evidence": [{"source": "hostnames", "detail": "payments-api.prod.example.com"}],
    "limitations": [],
    "coverage": {"completeness_state": "complete"},
    "drilldowns": {
        "repo_context": {"repo_id": "repository:r_ab12cd34"},
        "repo_summary": {"repo_name": "payments-api"},
        "deployment_chain": {"service_name": "payments-api"},
    },
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
