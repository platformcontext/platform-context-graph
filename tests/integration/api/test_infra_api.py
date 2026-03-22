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


def test_infra_resource_search_returns_canonical_matches_from_entity_resolution() -> (
    None
):
    calls: list[dict[str, object]] = []

    def resolve_entity(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "matches": [
                {
                    "ref": {
                        "id": "cloud-resource:shared-payments-prod",
                        "type": "cloud_resource",
                        "name": "shared-payments-prod",
                    },
                    "score": 0.97,
                }
            ]
        }

    services = SimpleNamespace(
        database=object(),
        entity_resolution=SimpleNamespace(resolve_entity=resolve_entity),
        infra=SimpleNamespace(),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/infra/resources/search", json={"query": "payments-rds", "limit": 4}
        )

    assert response.status_code == 200
    assert (
        response.json()["matches"][0]["ref"]["id"]
        == "cloud-resource:shared-payments-prod"
    )
    assert calls == [
        {
            "database": services.database,
            "query": "payments-rds",
            "types": [
                "k8s_resource",
                "terraform_module",
                "terraform_resource",
                "cloud_resource",
            ],
            "kinds": None,
            "environment": None,
            "repo_id": None,
            "exact": False,
            "limit": 4,
        }
    ]


def test_infra_relationships_and_ecosystem_overview_are_exposed() -> None:
    relationship_calls: list[dict[str, object]] = []
    overview_calls: list[object] = []

    def get_infra_relationships(
        database: object, **kwargs: object
    ) -> dict[str, object]:
        relationship_calls.append({"database": database, **kwargs})
        return {"query_type": "what_deploys", "results": [{"app_name": "payments"}]}

    def get_ecosystem_overview(database: object) -> dict[str, object]:
        overview_calls.append(database)
        return {"ecosystem": {"name": "payments-platform"}}

    services = SimpleNamespace(
        database=object(),
        entity_resolution=SimpleNamespace(resolve_entity=lambda *_args, **_kwargs: {}),
        infra=SimpleNamespace(
            get_infra_relationships=get_infra_relationships,
            get_ecosystem_overview=get_ecosystem_overview,
        ),
    )

    with _make_client(query_services=services) as client:
        relationships = client.post(
            "/api/v0/infra/relationships",
            json={"relationship_type": "what_deploys", "target": "payments-api"},
        )
        overview = client.get("/api/v0/ecosystem/overview")

    assert relationships.status_code == 200
    assert overview.status_code == 200
    assert relationship_calls == [
        {
            "database": services.database,
            "target": "payments-api",
            "relationship_type": "what_deploys",
            "environment": None,
        }
    ]
    assert overview_calls == [services.database]
