"""Tests for lightweight query package import behavior."""

from __future__ import annotations

import importlib
import sys


def test_query_package_lazy_loads_shared_projection_tuning(monkeypatch) -> None:
    """The query package should not import tuning helpers until requested."""

    monkeypatch.delitem(
        sys.modules,
        "platform_context_graph.query.shared_projection_tuning",
        raising=False,
    )
    monkeypatch.delitem(sys.modules, "platform_context_graph.query", raising=False)

    query_pkg = importlib.import_module("platform_context_graph.query")

    assert "platform_context_graph.query.shared_projection_tuning" not in sys.modules
    tuning_module = query_pkg.shared_projection_tuning
    assert (
        tuning_module.__name__
        == "platform_context_graph.query.shared_projection_tuning"
    )
    assert "platform_context_graph.query.shared_projection_tuning" in sys.modules


def test_query_package_lazy_loads_additional_submodules(monkeypatch) -> None:
    """The query package should resolve non-eager submodules on demand."""

    monkeypatch.delitem(
        sys.modules,
        "platform_context_graph.query.shared_projection_tuning_format",
        raising=False,
    )
    monkeypatch.delitem(sys.modules, "platform_context_graph.query", raising=False)

    query_pkg = importlib.import_module("platform_context_graph.query")

    assert (
        "platform_context_graph.query.shared_projection_tuning_format"
        not in sys.modules
    )
    story_module = query_pkg.shared_projection_tuning_format
    assert (
        story_module.__name__
        == "platform_context_graph.query.shared_projection_tuning_format"
    )
    assert "platform_context_graph.query.shared_projection_tuning_format" in sys.modules
