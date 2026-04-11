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


def test_explain_dependency_path_returns_explanation() -> None:
    calls: list[dict[str, object]] = []

    def explain_dependency_path(
        database: object, **kwargs: object
    ) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {"hops": [{"type": "USES"}], "summary": {"hop_count": 1}}

    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(explain_dependency_path=explain_dependency_path),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/paths/explain",
            json={
                "source": "workload:payments-api",
                "target": "cloud-resource:shared-payments-prod",
            },
        )

    assert response.status_code == 200
    assert response.json()["summary"]["hop_count"] == 1
    assert calls == [
        {
            "database": services.database,
            "source": "workload:payments-api",
            "target": "cloud-resource:shared-payments-prod",
            "environment": None,
        }
    ]


def test_explain_dependency_path_accepts_content_entities() -> None:
    calls: list[dict[str, object]] = []

    services = SimpleNamespace(
        database=object(),
        impact=SimpleNamespace(
            explain_dependency_path=lambda database, **kwargs: (
                calls.append({"database": database, **kwargs})
                or {"hops": [], "summary": {"hop_count": 0}}
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/paths/explain",
            json={
                "source": "content-entity:e_ab12cd34ef56",
                "target": "repository:r_ab12cd34",
            },
        )

    assert response.status_code == 200
    assert calls == [
        {
            "database": services.database,
            "source": "content-entity:e_ab12cd34ef56",
            "target": "repository:r_ab12cd34",
            "environment": None,
        }
    ]
