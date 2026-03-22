from __future__ import annotations

import inspect

from platform_context_graph.cli import visualizer
from platform_context_graph.core import falkor_worker
from platform_context_graph.tools.graph_builder import GraphBuilder


def test_graph_builder_looks_for_pcgignore():
    source = inspect.getsource(GraphBuilder.build_graph_from_path_async)
    assert ".pcgignore" in source
    assert ".cgcignore" not in source


def test_falkor_worker_uses_pcg_health_check_graph():
    source = inspect.getsource(falkor_worker.run_worker)
    assert "__pcg_health_check" in source
    assert "__cgc_health_check" not in source


def test_visualizer_uses_pcg_filename_prefix():
    assert visualizer.generate_filename().startswith("pcg_viz_")
