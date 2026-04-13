"""Smoke tests for the remaining Python package skeleton during Go migration."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "platform_context_graph.app",
        "platform_context_graph.automation",
        "platform_context_graph.collectors",
        "platform_context_graph.collectors.git",
        "platform_context_graph.content",
        "platform_context_graph.graph",
        "platform_context_graph.parsers",
        "platform_context_graph.platform",
        "platform_context_graph.query",
    ],
)
def test_phase1_package_skeleton_imports(module_name: str) -> None:
    """The remaining Python package roots should still be importable."""

    assert importlib.import_module(module_name) is not None
