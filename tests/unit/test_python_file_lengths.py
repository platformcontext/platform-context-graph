from __future__ import annotations

from pathlib import Path

from scripts import check_python_file_lengths


def test_find_violations_skips_exempt_paths(tmp_path: Path) -> None:
    repo_root = tmp_path
    src_root = repo_root / "src"
    package_root = src_root / "platform_context_graph"
    package_root.mkdir(parents=True)

    compliant = package_root / "ok.py"
    compliant.write_text("print('ok')\n", encoding="utf-8")

    exempt_dir = package_root / "generated"
    exempt_dir.mkdir()
    exempt_file = exempt_dir / "big.py"
    exempt_file.write_text("line\n" * 900, encoding="utf-8")

    violations = check_python_file_lengths.find_violations(
        repo_root=repo_root,
        scan_root=src_root,
        max_lines=5,
        exemptions=(Path("src/platform_context_graph/generated"),),
    )

    assert violations == []


def test_find_violations_reports_oversized_handwritten_modules(tmp_path: Path) -> None:
    repo_root = tmp_path
    src_root = repo_root / "src"
    package_root = src_root / "platform_context_graph"
    package_root.mkdir(parents=True)

    oversized = package_root / "oversized.py"
    oversized.write_text("line\n" * 6, encoding="utf-8")

    violations = check_python_file_lengths.find_violations(
        repo_root=repo_root,
        scan_root=src_root,
        max_lines=5,
        exemptions=(),
    )

    assert violations == [
        check_python_file_lengths.FileLengthViolation(
            path=Path("src/platform_context_graph/oversized.py"),
            line_count=6,
            max_lines=5,
        )
    ]


def test_main_returns_zero_when_all_files_pass(tmp_path: Path, monkeypatch) -> None:
    src_root = tmp_path / "src"
    module_path = src_root / "platform_context_graph" / "small.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    result = check_python_file_lengths.main(["--max-lines", "5"])

    assert result == 0


def test_build_exemptions_loads_baseline_file(tmp_path: Path, monkeypatch) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    exemptions_file = scripts_dir / "python_file_length_exemptions.txt"
    exemptions_file.write_text(
        "# baseline exemptions\nsrc/platform_context_graph/legacy.py\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exemptions = check_python_file_lengths.build_exemptions([])

    assert Path("src/platform_context_graph/legacy.py") in exemptions
