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


def test_repository_story_route_uses_repository_story_query() -> None:
    calls: list[dict[str, object]] = []

    def get_repository_story(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "subject": {
                "id": "repository:r_ab12cd34",
                "type": "repository",
                "name": "payments-api",
            },
            "story": ["Payments API serves card-present transactions."],
            "story_sections": [
                {
                    "id": "deployment",
                    "title": "Deployment",
                    "summary": "GitHub Actions deploy onto EKS.",
                }
            ],
            "deployment_overview": {"platforms": [{"kind": "eks"}]},
            "evidence": [],
            "limitations": ["entrypoint_unknown"],
            "coverage": {"completeness_state": "partial"},
            "drilldowns": {"repo_context": {"repo_id": "repository:r_ab12cd34"}},
        }

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(get_repository_story=get_repository_story),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/repositories/repository:r_ab12cd34/story")

    assert response.status_code == 200
    assert response.json()["subject"]["id"] == "repository:r_ab12cd34"
    assert response.json()["story_sections"][0]["id"] == "deployment"
    assert calls == [
        {"database": services.database, "repo_id": "repository:r_ab12cd34"}
    ]


def test_workload_story_route_supports_environment_scope() -> None:
    calls: list[dict[str, object]] = []

    def get_workload_story(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "subject": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            },
            "story": ["Prod traffic lands on payments-api running in EKS."],
            "story_sections": [
                {
                    "id": "runtime",
                    "title": "Runtime",
                    "summary": "prod instance runs in EKS.",
                }
            ],
            "deployment_overview": {"platforms": [{"kind": "eks"}]},
            "evidence": [],
            "limitations": [],
            "coverage": None,
            "drilldowns": {
                "workload_context": {"workload_id": "workload:payments-api"}
            },
        }

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_workload_story=get_workload_story),
    )

    with _make_client(query_services=services) as client:
        response = client.get(
            "/api/v0/workloads/workload:payments-api/story?environment=prod"
        )

    assert response.status_code == 200
    assert (
        response.json()["story"][0]
        == "Prod traffic lands on payments-api running in EKS."
    )
    assert calls == [
        {
            "database": services.database,
            "workload_id": "workload:payments-api",
            "environment": "prod",
        }
    ]


def test_service_story_route_preserves_service_alias_errors() -> None:
    def get_service_story(_database: object, **_kwargs: object) -> dict[str, object]:
        raise ServiceAliasError(
            "Workload 'workload:ledger-worker' is not a service and cannot be addressed via service alias"
        )

    services = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(get_service_story=get_service_story),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/services/workload:ledger-worker/story")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid service identifier"
