"""Tests for lazy imports in runtime admin command wiring."""

from __future__ import annotations

import importlib
import sys


def test_runtime_admin_lazy_loads_tuning_builder(monkeypatch) -> None:
    """Runtime admin should defer the heavy tuning builder until invoked."""

    monkeypatch.delitem(
        sys.modules,
        "platform_context_graph.query.shared_projection_tuning",
        raising=False,
    )
    monkeypatch.delitem(
        sys.modules,
        "platform_context_graph.cli.remote_commands",
        raising=False,
    )
    monkeypatch.delitem(
        sys.modules,
        "platform_context_graph.cli.commands.runtime_admin",
        raising=False,
    )

    runtime_admin = importlib.import_module(
        "platform_context_graph.cli.commands.runtime_admin"
    )

    assert "platform_context_graph.query.shared_projection_tuning" not in sys.modules
    report = runtime_admin._build_tuning_report(include_platform=False)

    assert report["recommended"]["setting"] == "4x2"
    assert "platform_context_graph.query.shared_projection_tuning" in sys.modules
