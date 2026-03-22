from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError

import pytest


def test_create_app_exposes_versioned_docs_endpoints() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")
    cli_main = importlib.import_module("platform_context_graph.cli.main")
    app = api_app.create_app()
    client = TestClient(app)

    assert app.title == "PlatformContextGraph HTTP API"
    assert app.version == cli_main.get_version()
    assert app.openapi_url == "/api/v0/openapi.json"
    assert app.docs_url == "/api/v0/docs"
    assert app.redoc_url == "/api/v0/redoc"

    schema = client.get("/api/v0/openapi.json").json()
    assert schema["info"]["title"] == app.title
    assert schema["info"]["version"] == app.version
    assert client.get("/api/v0/openapi.json").status_code == 200
    assert client.get("/api/v0/docs").status_code == 200
    assert client.get("/api/v0/redoc").status_code == 200


def test_create_app_database_only_override_isolates_health_route() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")
    dependencies = importlib.import_module("platform_context_graph.api.dependencies")

    calls: list[str] = []

    def fake_database() -> dict[str, str]:
        calls.append("database")
        return {"name": "fake-db"}

    def fail_if_real_db_is_used() -> None:
        raise AssertionError("real database should not be touched")

    app = api_app.create_app(database_dependency=fake_database)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            dependencies, "get_database_manager", fail_if_real_db_is_used
        )
        with TestClient(app) as client:
            response = client.get("/api/v0/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == ["database"]


def test_create_app_query_only_override_isolates_health_route() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")
    dependencies = importlib.import_module("platform_context_graph.api.dependencies")

    calls: list[str] = []

    def fake_query_services() -> dict[str, str]:
        calls.append("query")
        return {"name": "fake-query-services"}

    def fail_if_real_db_is_used() -> None:
        raise AssertionError("real database should not be touched")

    app = api_app.create_app(query_services_dependency=fake_query_services)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            dependencies, "get_database_manager", fail_if_real_db_is_used
        )
        with TestClient(app) as client:
            response = client.get("/api/v0/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == ["query"]


def test_create_app_query_override_supports_async_yield_dependencies() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")
    dependencies = importlib.import_module("platform_context_graph.api.dependencies")

    events: list[str] = []

    async def fake_query_services():
        events.append("enter")
        yield {"name": "fake-query-services"}
        events.append("exit")

    app = api_app.create_app()
    app.dependency_overrides[dependencies.get_query_services] = fake_query_services

    with TestClient(app) as client:
        response = client.get("/api/v0/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert events == ["enter", "exit"]


def test_app_dependency_overrides_on_exported_dependencies_still_apply_to_health_route() -> (
    None
):
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")
    dependencies = importlib.import_module("platform_context_graph.api.dependencies")

    calls: list[str] = []

    async def fake_database() -> dict[str, str]:
        calls.append("database")
        return {"name": "fake-db"}

    def fail_if_real_db_is_used() -> None:
        raise AssertionError("real database should not be touched")

    app = api_app.create_app()
    app.dependency_overrides[dependencies.get_database] = fake_database

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            dependencies, "get_database_manager", fail_if_real_db_is_used
        )
        with TestClient(app) as client:
            response = client.get("/api/v0/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == ["database"]


def test_create_app_uses_cli_version_fallback_when_package_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_app = importlib.import_module("platform_context_graph.api.app")
    cli_main = importlib.import_module("platform_context_graph.cli.main")

    def raise_missing_version(package_name: str) -> str:
        raise PackageNotFoundError(package_name)

    monkeypatch.setattr(api_app, "pkg_version", raise_missing_version)
    monkeypatch.setattr(cli_main, "pkg_version", raise_missing_version)

    app = api_app.create_app()
    assert app.version == cli_main.get_version()


def test_create_service_app_exposes_http_api_and_mcp_routes() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")

    app = api_app.create_service_app(
        query_services_dependency=lambda: {"query": "services"},
        mcp_server_dependency=lambda: None,
    )

    route_paths = {route.path for route in app.routes}
    assert "/mcp/sse" in route_paths
    assert "/mcp/message" in route_paths

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v0/health").status_code == 200
        assert (
            client.post(
                "/mcp/message", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            ).status_code
            == 503
        )


def test_service_app_factory_is_exported() -> None:
    api_app = importlib.import_module("platform_context_graph.api.app")
    assert hasattr(api_app, "create_service_app")
