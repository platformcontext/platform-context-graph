"""Public visualization entrypoints for CLI graph rendering."""

from __future__ import annotations

from .visualization.core import (
    _json_for_inline_script,
    _safe_json_dumps,
    check_visual_flag,
    console,
    escape_html,
    generate_filename,
    get_node_color,
    get_visualization_dir,
    save_and_open_visualization,
)
from .visualization.graphs import (
    visualize_call_chain,
    visualize_call_graph,
    visualize_cypher_results,
    visualize_dependencies,
    visualize_inheritance_tree,
    visualize_overrides,
    visualize_search_results,
)
from .visualization.template import generate_html_template

__all__ = [
    "console",
    "_json_for_inline_script",
    "_safe_json_dumps",
    "check_visual_flag",
    "escape_html",
    "generate_filename",
    "generate_html_template",
    "get_node_color",
    "get_visualization_dir",
    "save_and_open_visualization",
    "visualize_call_chain",
    "visualize_call_graph",
    "visualize_cypher_results",
    "visualize_dependencies",
    "visualize_inheritance_tree",
    "visualize_overrides",
    "visualize_search_results",
]
