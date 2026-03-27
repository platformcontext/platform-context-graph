from __future__ import annotations

from pathlib import Path

import pytest

from platform_context_graph.utils.source_text import read_source_text


def test_read_source_text_falls_back_to_cp1252(tmp_path: Path) -> None:
    path = tmp_path / "legacy.js"
    path.write_bytes("var price = '£9';\n".encode("cp1252"))

    assert read_source_text(path) == "var price = '£9';\n"


def test_read_source_text_rejects_oversized_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "oversized.js"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "1")

    with pytest.raises(ValueError, match="exceeds configured maximum size"):
        read_source_text(path)
