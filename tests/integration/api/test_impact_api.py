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


def test_change_surface_returns_impacted_entities() -> None:
    calls: list[dict[str, object]] = []

    def find_change_surface(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {"impacted": [{"id": "workload:payments-api"}]}

    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(find_change_surface=find_change_surface),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/impact/change-surface",
            json={
                "target": "cloud-resource:shared-payments-prod",
                "environment": "prod",
            },
        )

    assert response.status_code == 200
    assert response.json()["impacted"][0]["id"] == "workload:payments-api"
    assert calls == [
        {
            "database": services.database,
            "target": "cloud-resource:shared-payments-prod",
            "environment": "prod",
        }
    ]


def test_change_surface_accepts_content_entities() -> None:
    calls: list[dict[str, object]] = []

    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(
            find_change_surface=lambda database, **kwargs: (
                calls.append({"database": database, **kwargs}) or {"impacted": []}
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/impact/change-surface",
            json={"target": "content-entity:e_ab12cd34ef56"},
        )

    assert response.status_code == 200
    assert calls == [
        {
            "database": services.database,
            "target": "content-entity:e_ab12cd34ef56",
            "environment": None,
        }
    ]
