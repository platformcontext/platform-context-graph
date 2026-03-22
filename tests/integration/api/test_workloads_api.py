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


def test_workload_context_supports_logical_and_environment_views() -> None:
    calls: list[dict[str, object]] = []

    def get_workload_context(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        result = {
            "workload": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            }
        }
        if kwargs.get("environment"):
            result["instance"] = {
                "id": "workload-instance:payments-api:prod",
                "type": "workload_instance",
                "kind": "service",
                "name": "payments-api",
                "environment": "prod",
                "workload_id": "workload:payments-api",
            }
        else:
            result["instances"] = [
                {
                    "id": "workload-instance:payments-api:prod",
                    "type": "workload_instance",
                    "kind": "service",
                    "name": "payments-api",
                    "environment": "prod",
                    "workload_id": "workload:payments-api",
                }
            ]
        return result

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_workload_context=get_workload_context),
    )

    with _make_client(query_services=services) as client:
        logical = client.get("/api/v0/workloads/workload:payments-api/context")
        instance = client.get(
            "/api/v0/workloads/workload:payments-api/context?environment=prod"
        )

    assert logical.status_code == 200
    assert logical.json()["workload"]["id"] == "workload:payments-api"
    assert instance.status_code == 200
    assert instance.json()["instance"]["id"] == "workload-instance:payments-api:prod"
    assert calls == [
        {
            "database": services.database,
            "workload_id": "workload:payments-api",
            "environment": None,
        },
        {
            "database": services.database,
            "workload_id": "workload:payments-api",
            "environment": "prod",
        },
    ]


def test_workload_context_rejects_non_canonical_ids_with_problem_details() -> None:
    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(
            get_workload_context=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/workloads/payments-api/context")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical workload identifier"


def test_workload_context_returns_404_when_environment_instance_is_missing() -> None:
    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(
            get_workload_context=lambda *_args, **_kwargs: {
                "error": "Workload 'workload:payments-api' has no instance for environment 'prod'"
            }
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get(
            "/api/v0/workloads/workload:payments-api/context?environment=prod"
        )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Workload not found",
        "status": 404,
        "detail": "Workload 'workload:payments-api' has no instance for environment 'prod'",
        "instance": "/api/v0/workloads/workload:payments-api/context",
    }
