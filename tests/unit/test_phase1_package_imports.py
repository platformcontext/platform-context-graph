"""Smoke tests for the Phase 1 architecture package skeleton."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "platform_context_graph.app",
        "platform_context_graph.collectors",
        "platform_context_graph.collectors.git",
        "platform_context_graph.facts",
        "platform_context_graph.resolution",
        "platform_context_graph.graph",
        "platform_context_graph.parsers",
        "platform_context_graph.platform",
    ],
)
def test_phase1_package_skeleton_imports(module_name: str) -> None:
    """The Phase 1 target packages should be importable."""

    assert importlib.import_module(module_name) is not None
