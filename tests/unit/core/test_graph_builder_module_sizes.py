from __future__ import annotations

from pathlib import Path

_LEGACY_MAX_LINES = {
    "graph_builder_indexing_execution.py": 791,
    "graph_builder_persistence.py": 570,
    "graph_builder_persistence_batch.py": 520,
}


def test_graph_builder_modules_stay_within_size_limit() -> None:
    """Keep the GraphBuilder facade split readable and mechanically enforceable."""
    tools_dir = (
        Path(__file__).resolve().parents[3] / "src" / "platform_context_graph" / "tools"
    )

    touched_modules = sorted(tools_dir.glob("graph_builder*.py"))

    assert touched_modules
    for module_path in touched_modules:
        line_count = len(module_path.read_text().splitlines())
        limit = _LEGACY_MAX_LINES.get(module_path.name, 500)
        assert line_count <= limit, f"{module_path.name} has {line_count} lines"
