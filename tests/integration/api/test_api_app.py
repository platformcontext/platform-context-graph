from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

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


def test_create_service_app_starts_without_code_watcher_for_api_role() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient
    from unittest.mock import MagicMock

    api_app = importlib.import_module("platform_context_graph.api.app")

    server = SimpleNamespace(
        code_watcher=None,
        shutdown=MagicMock(),
    )

    app = api_app.create_service_app(
        query_services_dependency=lambda: {"query": "services"},
        mcp_server_dependency=lambda: server,
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    server.shutdown.assert_called_once()


def test_create_app_exposes_repository_ingester_status_route() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")

    class _StatusModule:
        KNOWN_INGESTERS = ("repository",)

        @staticmethod
        def get_ingester_status(_database, *, ingester="repository"):
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": ingester,
                "source_mode": "githubOrg",
                "status": "indexing",
                "active_run_id": "run-123",
                "last_attempt_at": "2026-03-22T12:00:00+00:00",
                "last_success_at": None,
                "next_retry_at": None,
                "last_error_kind": None,
                "last_error_message": None,
                "repository_count": 200,
                "pulled_repositories": 180,
                "in_sync_repositories": 20,
                "pending_repositories": 200,
                "completed_repositories": 0,
                "failed_repositories": 0,
                "scan_request_state": "idle",
                "scan_request_token": None,
                "scan_requested_at": None,
                "scan_requested_by": None,
                "scan_started_at": None,
                "scan_completed_at": None,
                "scan_error_message": None,
                "updated_at": "2026-03-22T12:00:00+00:00",
            }

    app = api_app.create_app(
        query_services_dependency=lambda: SimpleNamespace(
            database=object(),
            status=_StatusModule(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v0/ingesters/repository")

    assert response.status_code == 200
    assert response.json()["runtime_family"] == "ingester"
    assert response.json()["ingester"] == "repository"
    assert response.json()["status"] == "indexing"
    assert response.json()["pulled_repositories"] == 180
    assert response.json()["in_sync_repositories"] == 20


def test_create_app_exposes_ingester_status_and_scan_routes() -> None:
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")

    class _StatusModule:
        KNOWN_INGESTERS = ("repository",)

        @staticmethod
        def list_ingesters(_database):
            return [
                {
                    "runtime_family": "ingester",
                    "ingester": "repository",
                    "provider": "repository",
                    "source_mode": "githubOrg",
                    "status": "idle",
                    "active_run_id": "run-123",
                    "last_attempt_at": "2026-03-22T12:00:00+00:00",
                    "last_success_at": "2026-03-22T12:01:00+00:00",
                    "next_retry_at": None,
                    "last_error_kind": None,
                    "last_error_message": None,
                    "repository_count": 200,
                    "pulled_repositories": 200,
                    "in_sync_repositories": 200,
                    "pending_repositories": 0,
                    "completed_repositories": 200,
                    "failed_repositories": 0,
                    "scan_request_state": "idle",
                    "scan_request_token": None,
                    "scan_requested_at": None,
                    "scan_requested_by": None,
                    "scan_started_at": None,
                    "scan_completed_at": None,
                    "scan_error_message": None,
                    "updated_at": "2026-03-22T12:01:00+00:00",
                }
            ]

        @staticmethod
        def get_ingester_status(_database, *, ingester="repository"):
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": "repository",
                "source_mode": "githubOrg",
                "status": "idle",
                "active_run_id": "run-123",
                "last_attempt_at": "2026-03-22T12:00:00+00:00",
                "last_success_at": "2026-03-22T12:01:00+00:00",
                "next_retry_at": None,
                "last_error_kind": None,
                "last_error_message": None,
                "repository_count": 200,
                "pulled_repositories": 200,
                "in_sync_repositories": 200,
                "pending_repositories": 0,
                "completed_repositories": 200,
                "failed_repositories": 0,
                "scan_request_state": "idle",
                "scan_request_token": None,
                "scan_requested_at": None,
                "scan_requested_by": None,
                "scan_started_at": None,
                "scan_completed_at": None,
                "scan_error_message": None,
                "updated_at": "2026-03-22T12:01:00+00:00",
            }

        @staticmethod
        def request_ingester_scan_control(
            _database, *, ingester="repository", requested_by="api"
        ):
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": "repository",
                "accepted": True,
                "scan_request_token": "scan-123",
                "scan_request_state": "pending",
                "scan_requested_at": "2026-03-22T12:05:00+00:00",
                "scan_requested_by": requested_by,
            }

    app = api_app.create_app(
        query_services_dependency=lambda: SimpleNamespace(
            database=object(),
            status=_StatusModule(),
        )
    )

    with TestClient(app) as client:
        list_response = client.get("/api/v0/ingesters")
        status_response = client.get("/api/v0/ingesters/repository")
        scan_response = client.post("/api/v0/ingesters/repository/scan")

    assert list_response.status_code == 200
    assert list_response.json()[0]["ingester"] == "repository"
    assert status_response.status_code == 200
    assert status_response.json()["ingester"] == "repository"
    assert scan_response.status_code == 200
    assert scan_response.json()["accepted"] is True
    assert scan_response.json()["ingester"] == "repository"
    assert scan_response.json()["scan_request_state"] == "pending"


def test_service_app_factory_is_exported() -> None:
    api_app = importlib.import_module("platform_context_graph.api.app")
    assert hasattr(api_app, "create_service_app")
