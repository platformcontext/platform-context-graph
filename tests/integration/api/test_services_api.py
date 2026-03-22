from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from platform_context_graph.query.context import ServiceAliasError

pytest.importorskip("httpx")
from starlette.testclient import TestClient


def _make_client(*, query_services: object) -> TestClient:
    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: query_services)
    )


def test_service_context_returns_service_alias_view() -> None:
    calls: list[dict[str, object]] = []

    def get_service_context(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "requested_as": "service",
            "workload": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            },
        }

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_service_context=get_service_context),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/services/workload:payments-api/context")

    assert response.status_code == 200
    assert response.json()["requested_as"] == "service"
    assert calls == [
        {
            "database": services.database,
            "workload_id": "workload:payments-api",
            "environment": None,
        }
    ]


def test_service_context_rejects_non_service_workloads_with_problem_details() -> None:
    def get_service_context(_database: object, **_kwargs: object) -> dict[str, object]:
        raise ServiceAliasError(
            "Workload 'workload:ledger-worker' is not a service and cannot be addressed via service alias"
        )

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_service_context=get_service_context),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/services/workload:ledger-worker/context")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Invalid service identifier",
        "status": 400,
        "detail": "Workload 'workload:ledger-worker' is not a service and cannot be addressed via service alias",
        "instance": "/api/v0/services/workload:ledger-worker/context",
    }
