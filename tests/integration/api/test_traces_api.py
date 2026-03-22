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


def test_trace_resource_to_code_returns_paths() -> None:
    calls: list[dict[str, object]] = []

    def trace_resource_to_code(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {"paths": [{"summary": {"hop_count": 2}}]}

    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(trace_resource_to_code=trace_resource_to_code),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/traces/resource-to-code",
            json={
                "start": "cloud-resource:shared-payments-prod",
                "environment": "prod",
                "max_depth": 4,
            },
        )

    assert response.status_code == 200
    assert response.json()["paths"][0]["summary"]["hop_count"] == 2
    assert calls == [
        {
            "database": services.database,
            "start": "cloud-resource:shared-payments-prod",
            "environment": "prod",
            "max_depth": 4,
        }
    ]


def test_trace_resource_to_code_rejects_non_canonical_start_ids() -> None:
    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(
            trace_resource_to_code=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/traces/resource-to-code", json={"start": "payments-rds"}
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical entity identifier"


def test_trace_resource_to_code_rejects_content_entities() -> None:
    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(
            trace_resource_to_code=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/traces/resource-to-code",
            json={"start": "content-entity:e_ab12cd34ef56"},
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical entity identifier"
