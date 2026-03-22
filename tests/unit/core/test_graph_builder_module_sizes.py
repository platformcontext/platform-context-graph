from __future__ import annotations

from pathlib import Path


def test_graph_builder_modules_stay_within_size_limit() -> None:
    """Keep the GraphBuilder facade split readable and mechanically enforceable."""
    tools_dir = (
        Path(__file__).resolve().parents[3] / "src" / "platform_context_graph" / "tools"
    )

    touched_modules = sorted(tools_dir.glob("graph_builder*.py"))

    assert touched_modules
    for module_path in touched_modules:
        line_count = len(module_path.read_text().splitlines())
        assert line_count <= 500, f"{module_path.name} has {line_count} lines"
