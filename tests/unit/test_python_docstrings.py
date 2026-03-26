from __future__ import annotations

from pathlib import Path

from scripts import check_python_docstrings


def test_find_violations_skips_exempt_paths(tmp_path: Path) -> None:
    repo_root = tmp_path
    src_root = repo_root / "src"
    package_root = src_root / "platform_context_graph"
    package_root.mkdir(parents=True)

    exempt_dir = package_root / "generated"
    exempt_dir.mkdir()
    exempt_file = exempt_dir / "generated_module.py"
    exempt_file.write_text(
        "class Generated:\n" "    def render(self):\n" "        return 'ok'\n",
        encoding="utf-8",
    )

    violations = check_python_docstrings.find_violations(
        repo_root=repo_root,
        scan_root=src_root,
        exemptions=(Path("src/platform_context_graph/generated"),),
    )

    assert violations == []


def test_find_violations_reports_recursive_missing_docstrings(tmp_path: Path) -> None:
    repo_root = tmp_path
    src_root = repo_root / "src"
    package_root = src_root / "platform_context_graph"
    package_root.mkdir(parents=True)

    module_path = package_root / "sample.py"
    module_path.write_text(
        "class Sample:\n"
        "    def __init__(self):\n"
        "        self.value = 1\n"
        "\n"
        "    def render(self):\n"
        "        return self.value\n",
        encoding="utf-8",
    )

    violations = check_python_docstrings.find_violations(
        repo_root=repo_root,
        scan_root=src_root,
        exemptions=(),
    )

    assert violations == [
        check_python_docstrings.DocstringViolation(
            path=Path("src/platform_context_graph/sample.py"),
            object_type="module",
            qualified_name="sample",
            line_number=1,
        ),
        check_python_docstrings.DocstringViolation(
            path=Path("src/platform_context_graph/sample.py"),
            object_type="class",
            qualified_name="Sample",
            line_number=1,
        ),
        check_python_docstrings.DocstringViolation(
            path=Path("src/platform_context_graph/sample.py"),
            object_type="function",
            qualified_name="Sample.__init__",
            line_number=2,
        ),
        check_python_docstrings.DocstringViolation(
            path=Path("src/platform_context_graph/sample.py"),
            object_type="function",
            qualified_name="Sample.render",
            line_number=5,
        ),
    ]


def test_main_returns_zero_when_all_files_have_docstrings(
    tmp_path: Path, monkeypatch
) -> None:
    src_root = tmp_path / "src"
    module_path = src_root / "platform_context_graph" / "small.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(
        '"""Small module."""\n\n'
        "class Small:\n"
        '    """Small class."""\n\n'
        "    def render(self) -> str:\n"
        '        """Render a small value."""\n'
        "        return 'ok'\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    result = check_python_docstrings.main([])

    assert result == 0


def test_build_exemptions_loads_baseline_file(tmp_path: Path, monkeypatch) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    exemptions_file = scripts_dir / "python_docstring_exemptions.txt"
    exemptions_file.write_text(
        "# baseline exemptions\nsrc/platform_context_graph/legacy.py\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exemptions = check_python_docstrings.build_exemptions([])

    assert Path("src/platform_context_graph/legacy.py") in exemptions
