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


def test_repository_routes_expose_context_and_stats_by_canonical_id() -> None:
    context_calls: list[dict[str, object]] = []
    stats_calls: list[dict[str, object]] = []

    def get_repository_context(database: object, **kwargs: object) -> dict[str, object]:
        context_calls.append({"database": database, **kwargs})
        return {"repository": {"id": "repository:r_ab12cd34", "name": "payments-api"}}

    def get_repository_stats(database: object, **kwargs: object) -> dict[str, object]:
        stats_calls.append({"database": database, **kwargs})
        return {"success": True, "stats": {"files": 10}}

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            get_repository_context=get_repository_context,
            get_repository_stats=get_repository_stats,
        ),
    )

    with _make_client(query_services=services) as client:
        context_response = client.get(
            "/api/v0/repositories/repository:r_ab12cd34/context"
        )
        stats_response = client.get("/api/v0/repositories/repository:r_ab12cd34/stats")

    assert context_response.status_code == 200
    assert stats_response.status_code == 200
    assert context_calls == [
        {"database": services.database, "repo_id": "repository:r_ab12cd34"}
    ]
    assert stats_calls == [
        {"database": services.database, "repo_id": "repository:r_ab12cd34"}
    ]


def test_repository_routes_expose_listing_via_query_services() -> None:
    list_calls: list[dict[str, object]] = []

    def list_repositories(database: object) -> dict[str, object]:
        list_calls.append({"database": database})
        return {
            "repositories": [{"id": "repository:r_ab12cd34", "name": "payments-api"}]
        }

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            list_repositories=list_repositories,
            get_repository_context=lambda *_args, **_kwargs: pytest.fail(
                "context should not be called"
            ),
            get_repository_stats=lambda *_args, **_kwargs: pytest.fail(
                "stats should not be called"
            ),
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/repositories")

    assert response.status_code == 200
    assert response.json() == {
        "repositories": [{"id": "repository:r_ab12cd34", "name": "payments-api"}]
    }
    assert list_calls == [{"database": services.database}]


def test_repository_routes_reject_non_canonical_ids_with_problem_details() -> None:
    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            get_repository_context=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            ),
            get_repository_stats=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            ),
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/repositories/payments-api/context")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical repository identifier"
