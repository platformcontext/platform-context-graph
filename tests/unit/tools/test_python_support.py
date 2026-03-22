from __future__ import annotations

from pathlib import Path

import nbformat

from platform_context_graph.tools.languages import python_support


def test_convert_notebook_to_temp_python_falls_back_without_nbconvert_template(
    tmp_path: Path, monkeypatch
) -> None:
    notebook_path = tmp_path / "example.ipynb"
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell("ignore"),
            nbformat.v4.new_code_cell("print('hello')"),
            nbformat.v4.new_code_cell("x = 1"),
        ]
    )
    notebook_path.write_text(nbformat.writes(notebook), encoding="utf-8")

    def raise_export_error(*_args, **_kwargs):
        raise RuntimeError("missing template")

    monkeypatch.setattr(
        python_support.PythonExporter,
        "from_notebook_node",
        raise_export_error,
    )

    temp_path = python_support.convert_notebook_to_temp_python(notebook_path)
    try:
        rendered = temp_path.read_text(encoding="utf-8")
    finally:
        temp_path.unlink(missing_ok=True)

    assert "print('hello')" in rendered
    assert "x = 1" in rendered
