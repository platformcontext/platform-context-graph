from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")
from starlette.testclient import TestClient


def _make_client(*, query_services: object) -> TestClient:
    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: query_services)
    )


def test_resolve_entity_returns_ranked_matches() -> None:
    calls: list[dict[str, object]] = []

    def resolve_entity(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "matches": [
                {
                    "ref": {
                        "id": "workload:payments-api",
                        "type": "workload",
                        "kind": "service",
                        "name": "payments-api",
                    },
                    "score": 0.98,
                }
            ]
        }

    services = SimpleNamespace(
        database=object(),
        entity_resolution=SimpleNamespace(resolve_entity=resolve_entity),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/entities/resolve",
            json={"query": "payments api", "types": ["workload"], "limit": 5},
        )

    assert response.status_code == 200
    assert response.json()["matches"][0]["ref"]["id"] == "workload:payments-api"
    assert calls == [
        {
            "database": services.database,
            "query": "payments api",
            "types": ["workload"],
            "kinds": None,
            "environment": None,
            "repo_id": None,
            "exact": False,
            "limit": 5,
        }
    ]


def test_resolve_entity_request_normalizes_public_type_aliases() -> None:
    calls: list[dict[str, object]] = []

    def resolve_entity(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {"matches": []}

    services = SimpleNamespace(
        database=object(),
        entity_resolution=SimpleNamespace(resolve_entity=resolve_entity),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/entities/resolve",
            json={
                "query": "api-node-search",
                "types": [
                    "argocd_application",
                    "argocd_applicationset",
                    "cloud-resource",
                    "workload-instance",
                ],
            },
        )

    assert response.status_code == 200
    assert [
        value.value if hasattr(value, "value") else value for value in calls[0]["types"]
    ] == [
        "k8s_resource",
        "k8s_resource",
        "cloud_resource",
        "workload_instance",
    ]


def test_entity_context_returns_context_for_canonical_id() -> None:
    calls: list[dict[str, object]] = []

    def get_entity_context(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "entity": {
                "id": "repository:r_ab12cd34",
                "type": "repository",
                "name": "payments-api",
                "path": "/srv/repos/payments-api",
            },
            "related": [],
        }

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_entity_context=get_entity_context),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/entities/repository:r_ab12cd34/context")

    assert response.status_code == 200
    assert response.json()["entity"]["id"] == "repository:r_ab12cd34"
    assert calls == [
        {
            "database": services.database,
            "entity_id": "repository:r_ab12cd34",
            "environment": None,
        }
    ]


def test_entity_context_rejects_non_canonical_ids_with_problem_details() -> None:
    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(
            get_entity_context=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/entities/payments-api/context")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Invalid canonical entity identifier",
        "status": 400,
        "detail": "Expected a canonical entity identifier. Use POST /api/v0/entities/resolve for fuzzy names, aliases, and raw paths.",
        "instance": "/api/v0/entities/payments-api/context",
    }


def test_entity_context_rejects_unknown_prefixes_with_problem_details() -> None:
    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(
            get_entity_context=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/entities/foo:bar/context")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical entity identifier"


def test_entity_context_accepts_content_entity_ids() -> None:
    calls: list[dict[str, object]] = []

    def get_entity_context(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "entity": {
                "id": "content-entity:e_ab12cd34ef56",
                "type": "content_entity",
                "name": "process_payment",
            },
            "repositories": [
                {
                    "id": "repository:r_ab12cd34",
                    "type": "repository",
                    "name": "payments-api",
                }
            ],
            "relative_path": "src/payments.py",
            "start_line": 10,
            "end_line": 18,
        }

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_entity_context=get_entity_context),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/entities/content-entity:e_ab12cd34ef56/context")

    assert response.status_code == 200
    assert response.json()["entity"]["id"] == "content-entity:e_ab12cd34ef56"
    assert calls == [
        {
            "database": services.database,
            "entity_id": "content-entity:e_ab12cd34ef56",
            "environment": None,
        }
    ]
