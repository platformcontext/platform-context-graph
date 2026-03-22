"""Regression tests for handwritten parser module size limits."""

from pathlib import Path

PARSER_MODULES = [
    "python.py",
    "swift.py",
    "elixir.py",
    "yaml_infra.py",
]


def test_handwritten_parser_facades_stay_under_500_lines() -> None:
    """Keep touched handwritten parser facades small enough to reason about."""
    languages_dir = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "platform_context_graph"
        / "tools"
        / "languages"
    )

    oversized_modules = []
    for module_name in PARSER_MODULES:
        line_count = len(
            (languages_dir / module_name).read_text(encoding="utf-8").splitlines()
        )
        if line_count > 500:
            oversized_modules.append((module_name, line_count))

    assert oversized_modules == []
