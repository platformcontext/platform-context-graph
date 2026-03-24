from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def _default_graph_missing_repository_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep repo-sync runtime tests opt-in for graph-healing behavior."""

    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")
    monkeypatch.setattr(
        sync,
        "graph_missing_repository_paths",
        lambda _repo_paths: [],
        raising=False,
    )
