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


def test_compare_environments_returns_left_right_snapshots() -> None:
    calls: list[dict[str, object]] = []

    def compare_environments(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "workload": {"id": "workload:payments-api"},
            "left": {"environment": "stage", "status": "present"},
            "right": {"environment": "prod", "status": "present"},
            "changed": {"cloud_resources": []},
        }

    services = SimpleNamespace(
        database=object(),
        compare=SimpleNamespace(compare_environments=compare_environments),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/environments/compare",
            json={
                "workload_id": "workload:payments-api",
                "left": "stage",
                "right": "prod",
            },
        )

    assert response.status_code == 200
    assert response.json()["left"]["environment"] == "stage"
    assert response.json()["right"]["environment"] == "prod"
    assert calls == [
        {
            "database": services.database,
            "workload_id": "workload:payments-api",
            "left": "stage",
            "right": "prod",
        }
    ]


def test_compare_environments_rejects_non_canonical_workload_ids() -> None:
    services = SimpleNamespace(
        database=object(),
        compare=SimpleNamespace(
            compare_environments=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/environments/compare",
            json={"workload_id": "payments-api", "left": "stage", "right": "prod"},
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical workload identifier"
