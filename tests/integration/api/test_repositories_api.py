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
    coverage_calls: list[dict[str, object]] = []

    def get_repository_context(database: object, **kwargs: object) -> dict[str, object]:
        context_calls.append({"database": database, **kwargs})
        return {"repository": {"id": "repository:r_ab12cd34", "name": "payments-api"}}

    def get_repository_stats(database: object, **kwargs: object) -> dict[str, object]:
        stats_calls.append({"database": database, **kwargs})
        return {"success": True, "stats": {"files": 10}}

    def get_repository_coverage(
        database: object, **kwargs: object
    ) -> dict[str, object]:
        coverage_calls.append({"database": database, **kwargs})
        return {
            "run_id": "run-123",
            "repo_id": "repository:r_ab12cd34",
            "status": "completed",
        }

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            get_repository_context=get_repository_context,
            get_repository_stats=get_repository_stats,
            get_repository_coverage=get_repository_coverage,
        ),
    )

    with _make_client(query_services=services) as client:
        context_response = client.get(
            "/api/v0/repositories/repository:r_ab12cd34/context"
        )
        stats_response = client.get("/api/v0/repositories/repository:r_ab12cd34/stats")
        coverage_response = client.get(
            "/api/v0/repositories/repository:r_ab12cd34/coverage"
        )

    assert context_response.status_code == 200
    assert stats_response.status_code == 200
    assert coverage_response.status_code == 200
    assert context_calls == [
        {"database": services.database, "repo_id": "repository:r_ab12cd34"}
    ]
    assert stats_calls == [
        {"database": services.database, "repo_id": "repository:r_ab12cd34"}
    ]
    assert coverage_calls == [
        {"database": services.database, "repo_id": "repository:r_ab12cd34"}
    ]


def test_repository_context_route_preserves_platforms_and_limitations() -> None:
    def get_repository_context(database: object, **kwargs: object) -> dict[str, object]:
        del database, kwargs
        return {
            "repository": {"id": "repository:r_ab12cd34", "name": "payments-api"},
            "platforms": [{"id": "platform:ecs:aws:cluster/node10", "kind": "ecs"}],
            "limitations": ["dns_unknown", "entrypoint_unknown"],
        }

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            get_repository_context=get_repository_context,
            get_repository_stats=lambda *_args, **_kwargs: pytest.fail(
                "stats should not be called"
            ),
            get_repository_coverage=lambda *_args, **_kwargs: pytest.fail(
                "coverage should not be called"
            ),
            list_repositories=lambda *_args, **_kwargs: pytest.fail(
                "listing should not be called"
            ),
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/repositories/repository:r_ab12cd34/context")

    assert response.status_code == 200
    assert response.json()["platforms"] == [
        {"id": "platform:ecs:aws:cluster/node10", "kind": "ecs"}
    ]
    assert response.json()["limitations"] == ["dns_unknown", "entrypoint_unknown"]


def test_run_level_repository_coverage_route_passes_filters() -> None:
    coverage_calls: list[dict[str, object]] = []

    def list_repository_coverage(
        database: object, **kwargs: object
    ) -> dict[str, object]:
        coverage_calls.append({"database": database, **kwargs})
        return {"run_id": "run-123", "repositories": []}

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            list_repositories=lambda *_args, **_kwargs: pytest.fail(
                "repository listing should not be called"
            ),
            get_repository_context=lambda *_args, **_kwargs: pytest.fail(
                "repository context should not be called"
            ),
            get_repository_stats=lambda *_args, **_kwargs: pytest.fail(
                "repository stats should not be called"
            ),
            get_repository_coverage=lambda *_args, **_kwargs: pytest.fail(
                "repository coverage should not be called"
            ),
            list_repository_coverage=list_repository_coverage,
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get(
            "/api/v0/index-runs/run-123/coverage?only_incomplete=true&limit=25"
        )

    assert response.status_code == 200
    assert coverage_calls == [
        {
            "database": services.database,
            "run_id": "run-123",
            "only_incomplete": True,
            "limit": 25,
        }
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
            get_repository_coverage=lambda *_args, **_kwargs: pytest.fail(
                "coverage should not be called"
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
            get_repository_coverage=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            ),
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/repositories/payments-api/context")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical repository identifier"
