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
    """The Git collector is now owned by Go (go/cmd/ingester)."""

    service_entrypoints = importlib.import_module(
        "platform_context_graph.app.service_entrypoints"
    )

    spec = service_entrypoints.get_service_entrypoint("git-collector")

    assert spec.service_role == "git-collector"
    assert spec.runtime_role == "ingester"
    assert spec.implemented is True
    # Go owns this now, Python runtime.ingester is deleted
    assert spec.import_path == "go:cmd/ingester"


def test_get_service_entrypoint_returns_resolution_engine_spec() -> None:
    """The resolution engine is now owned by Go (go/cmd/reducer)."""

    service_entrypoints = importlib.import_module(
        "platform_context_graph.app.service_entrypoints"
    )

    spec = service_entrypoints.get_service_entrypoint("resolution-engine")

    assert spec.service_role == "resolution-engine"
    assert spec.runtime_role == "resolution-engine"
    assert spec.implemented is True
    # Go owns this now, Python resolution.orchestration.runtime is deleted
    assert spec.import_path == "go:cmd/reducer"


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
