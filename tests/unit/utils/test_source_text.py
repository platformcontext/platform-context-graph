from __future__ import annotations

from pathlib import Path

from platform_context_graph.utils.source_text import read_source_text


def test_read_source_text_falls_back_to_cp1252(tmp_path: Path) -> None:
    path = tmp_path / "legacy.js"
    path.write_bytes("var price = '£9';\n".encode("cp1252"))

    assert read_source_text(path) == "var price = '£9';\n"
