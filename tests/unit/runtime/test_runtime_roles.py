"""Unit tests for runtime role naming."""

from __future__ import annotations

import importlib

import pytest


def test_get_runtime_role_prefers_ingester_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The split runtime should expose `ingester` as the non-API role."""

    roles = importlib.import_module("platform_context_graph.runtime.roles")

    monkeypatch.setenv("PCG_RUNTIME_ROLE", "ingester")

    assert roles.get_runtime_role() == "ingester"


def test_get_runtime_role_does_not_preserve_legacy_worker_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy `worker` should no longer be returned as an active runtime role."""

    roles = importlib.import_module("platform_context_graph.runtime.roles")

    monkeypatch.setenv("PCG_RUNTIME_ROLE", "worker")

    assert roles.get_runtime_role() == "combined"


def test_get_runtime_role_accepts_resolution_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standalone resolution-engine should keep its explicit runtime role."""

    roles = importlib.import_module("platform_context_graph.runtime.roles")

    monkeypatch.setenv("PCG_RUNTIME_ROLE", "resolution-engine")

    assert roles.get_runtime_role() == "resolution-engine"
