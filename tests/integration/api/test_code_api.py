from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from platform_context_graph.api.dependencies import QueryServices
from platform_context_graph.repository_identity import canonical_repository_id

pytest.importorskip("httpx")
from starlette.testclient import TestClient


def _make_client(*, query_services: object) -> TestClient:
    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: query_services)
    )


def test_code_routes_delegate_to_query_services() -> None:
    calls: dict[str, list[dict[str, object]]] = {
        "search": [],
        "relationships": [],
        "dead_code": [],
        "complexity": [],
    }

    def search_code(database: object, **kwargs: object) -> dict[str, object]:
        calls["search"].append({"database": database, **kwargs})
        return {"ranked_results": [{"path": "src/payments.py"}]}

    def get_code_relationships(database: object, **kwargs: object) -> dict[str, object]:
        calls["relationships"].append({"database": database, **kwargs})
        return {"results": [{"kind": "calls"}]}

    def find_dead_code(database: object, **kwargs: object) -> dict[str, object]:
        calls["dead_code"].append({"database": database, **kwargs})
        return {"potentially_unused_functions": [{"function_name": "legacy_helper"}]}

    def get_complexity(database: object, **kwargs: object) -> dict[str, object]:
        calls["complexity"].append({"database": database, **kwargs})
        return {"functions": [{"name": "hot_path", "complexity": 21}]}

    services = SimpleNamespace(
        database=object(),
        code=SimpleNamespace(
            search_code=search_code,
            get_code_relationships=get_code_relationships,
            find_dead_code=find_dead_code,
            get_complexity=get_complexity,
        ),
    )

    with _make_client(query_services=services) as client:
        search_response = client.post(
            "/api/v0/code/search",
            json={
                "query": "payments",
                "repo_id": "repository:r_ab12cd34",
                "scope": "workspace",
                "exact": True,
                "limit": 3,
            },
        )
        relationships_response = client.post(
            "/api/v0/code/relationships",
            json={
                "query_type": "callers",
                "target": "process_payment",
                "repo_id": "repository:r_ab12cd34",
            },
        )
        dead_code_response = client.post(
            "/api/v0/code/dead-code",
            json={
                "repo_path": "/srv/repos/payments-api",
                "exclude_decorated_with": ["app.command"],
            },
        )
        complexity_response = client.post(
            "/api/v0/code/complexity",
            json={"mode": "top", "limit": 5, "repo_id": "repository:r_ab12cd34"},
        )

    assert search_response.status_code == 200
    assert relationships_response.status_code == 200
    assert dead_code_response.status_code == 200
    assert complexity_response.status_code == 200
    assert calls["search"] == [
        {
            "database": services.database,
            "query": "payments",
            "repo_id": "repository:r_ab12cd34",
            "scope": "workspace",
            "exact": True,
            "limit": 3,
            "edit_distance": None,
        }
    ]
    assert calls["relationships"] == [
        {
            "database": services.database,
            "query_type": "callers",
            "target": "process_payment",
            "context": None,
            "repo_id": "repository:r_ab12cd34",
            "scope": "auto",
        }
    ]
    assert calls["dead_code"] == [
        {
            "database": services.database,
            "repo_path": "/srv/repos/payments-api",
            "exclude_decorated_with": ["app.command"],
        }
    ]
    assert calls["complexity"] == [
        {
            "database": services.database,
            "mode": "top",
            "limit": 5,
            "function_name": None,
            "path": None,
            "repo_id": "repository:r_ab12cd34",
            "scope": "auto",
        }
    ]


def test_code_search_rejects_non_canonical_repository_ids() -> None:
    services = SimpleNamespace(
        database=object(),
        code=SimpleNamespace(
            search_code=lambda *_args, **_kwargs: pytest.fail(
                "service should not be called"
            )
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.post(
            "/api/v0/code/search", json={"query": "payments", "repo_id": "payments-api"}
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid canonical repository identifier"


def test_code_search_resolves_canonical_repository_ids_before_querying_database() -> (
    None
):
    api_app = importlib.import_module("platform_context_graph.api.app")

    class FakeResult:
        def __init__(self, *, records=None):
            self._records = records or []

        def data(self):
            return self._records

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query: str, **_kwargs):
            if (
                "MATCH (r:Repository)" in query
                and "coalesce(r.local_path, r.path) as local_path" in query
            ):
                return FakeResult(
                    records=[
                        {
                            "id": canonical_repository_id(
                                remote_url="https://github.com/platformcontext/payments-api",
                                local_path="/repos/payments-api",
                            ),
                            "name": "payments-api",
                            "path": "/repos/payments-api",
                            "local_path": "/repos/payments-api",
                            "remote_url": "https://github.com/platformcontext/payments-api",
                            "repo_slug": "platformcontext/payments-api",
                            "has_remote": True,
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    class FakeDriver:
        def session(self):
            return FakeSession()

    class FakeDatabase:
        def __init__(self):
            self.search_calls: list[dict[str, object]] = []

        def get_driver(self):
            return FakeDriver()

        def find_related_code(self, query, fuzzy_search, edit_distance, repo_path=None):
            self.search_calls.append(
                {
                    "query": query,
                    "fuzzy_search": fuzzy_search,
                    "edit_distance": edit_distance,
                    "repo_path": repo_path,
                }
            )
            return {"ranked_results": [{"path": "src/payments.py"}]}

    database = FakeDatabase()
    canonical_repo_id = canonical_repository_id(
        remote_url="https://github.com/platformcontext/payments-api",
        local_path="/repos/payments-api",
    )

    with TestClient(
        api_app.create_app(
            query_services_dependency=lambda: QueryServices(database=database)
        )
    ) as client:
        response = client.post(
            "/api/v0/code/search",
            json={"query": "payments", "repo_id": canonical_repo_id, "exact": True},
        )

    assert response.status_code == 200
    assert database.search_calls == [
        {
            "query": "payments",
            "fuzzy_search": False,
            "edit_distance": 2,
            "repo_path": "/repos/payments-api",
        }
    ]
