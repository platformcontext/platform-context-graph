from __future__ import annotations

import importlib
import sys

import platform_context_graph.cli.helpers.runtime as runtime_helper_module
import platform_context_graph.mcp.server as mcp_server_module
import platform_context_graph.tools.graph_builder as graph_builder_module


_SEAM_MODULES = (
    "platform_context_graph.collectors.git.indexing",
    "platform_context_graph.collectors.git.parse_execution",
    "platform_context_graph.parsers.registry",
    "platform_context_graph.parsers.scip",
    "platform_context_graph.parsers.scip.indexing",
    "platform_context_graph.parsers.scip.parser",
)


def _clear_modules() -> None:
    for name in _SEAM_MODULES:
        sys.modules.pop(name, None)


def test_graph_builder_import_does_not_load_legacy_parse_or_scip_modules() -> None:
    """Importing GraphBuilder should not eagerly load Python parse fallback stacks."""

    _clear_modules()
    importlib.reload(graph_builder_module)

    assert "platform_context_graph.collectors.git.parse_execution" not in sys.modules
    assert "platform_context_graph.parsers.registry" not in sys.modules
    assert "platform_context_graph.parsers.scip" not in sys.modules
    assert "platform_context_graph.parsers.scip.indexing" not in sys.modules
    assert "platform_context_graph.parsers.scip.parser" not in sys.modules


def test_runtime_modules_do_not_eagerly_load_legacy_parse_or_scip_modules() -> None:
    """Normal runtime module imports should avoid legacy parse and SCIP stacks."""

    _clear_modules()
    importlib.reload(graph_builder_module)
    importlib.reload(runtime_helper_module)
    importlib.reload(mcp_server_module)

    assert "platform_context_graph.collectors.git.parse_execution" not in sys.modules
    assert "platform_context_graph.parsers.registry" not in sys.modules
    assert "platform_context_graph.parsers.scip" not in sys.modules
    assert "platform_context_graph.parsers.scip.indexing" not in sys.modules
    assert "platform_context_graph.parsers.scip.parser" not in sys.modules
