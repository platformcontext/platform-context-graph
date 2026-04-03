"""Tests for app-level Phase 1 service entrypoint scaffolding."""

from __future__ import annotations

import importlib


def test_get_service_entrypoint_returns_api_spec() -> None:
    """The API service role should resolve to an entrypoint spec."""

    service_entrypoints = importlib.import_module(
        "platform_context_graph.app.service_entrypoints"
    )

    spec = service_entrypoints.get_service_entrypoint("api")

    assert spec.service_role == "api"
    assert spec.runtime_role == "api"
    assert spec.implemented is True
    assert spec.import_path == "platform_context_graph.cli.main:start_http_api"


def test_get_service_entrypoint_returns_git_collector_spec() -> None:
    """The Git collector should be represented even before deeper moves land."""

    service_entrypoints = importlib.import_module(
        "platform_context_graph.app.service_entrypoints"
    )

    spec = service_entrypoints.get_service_entrypoint("git-collector")

    assert spec.service_role == "git-collector"
    assert spec.runtime_role == "ingester"
    assert spec.implemented is True
    assert (
        spec.import_path == "platform_context_graph.runtime.ingester:run_repo_sync_loop"
    )


def test_get_service_entrypoint_returns_resolution_engine_placeholder() -> None:
    """The resolution engine role should exist as a future explicit boundary."""

    service_entrypoints = importlib.import_module(
        "platform_context_graph.app.service_entrypoints"
    )

    spec = service_entrypoints.get_service_entrypoint("resolution-engine")

    assert spec.service_role == "resolution-engine"
    assert spec.runtime_role == "combined"
    assert spec.implemented is False


def test_get_service_entrypoint_rejects_unknown_role() -> None:
    """Unknown service roles should fail fast."""

    service_entrypoints = importlib.import_module(
        "platform_context_graph.app.service_entrypoints"
    )

    try:
        service_entrypoints.get_service_entrypoint("unknown-role")
    except ValueError as exc:
        assert "unknown-role" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown service role")
