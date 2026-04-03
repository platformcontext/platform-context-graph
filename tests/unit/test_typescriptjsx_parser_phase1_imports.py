"""Phase 1 import compatibility tests for the TypeScript JSX parser move."""

from pathlib import Path

from platform_context_graph.parsers.capabilities import load_language_capability_specs
from platform_context_graph.parsers.languages.typescriptjsx import (
    TypescriptJSXTreeSitterParser as NewTypescriptJSXTreeSitterParser,
)
from platform_context_graph.tools.languages.typescriptjsx import (
    TypescriptJSXTreeSitterParser as LegacyTypescriptJSXTreeSitterParser,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_typescriptjsx_parser_moves_to_parsers_package() -> None:
    """Expose the TypeScript JSX parser from the new parsers package."""
    assert NewTypescriptJSXTreeSitterParser.__module__ == (
        "platform_context_graph.parsers.languages.typescriptjsx"
    )


def test_legacy_typescriptjsx_parser_reexports_new_parser() -> None:
    """Keep legacy imports working during the Phase 1 package migration."""
    assert LegacyTypescriptJSXTreeSitterParser is NewTypescriptJSXTreeSitterParser


def test_typescriptjsx_capability_spec_uses_new_entrypoint() -> None:
    """Point the TypeScript JSX capability spec at the new parser package."""
    specs = load_language_capability_specs(REPO_ROOT)
    spec = next(item for item in specs if item["language"] == "typescriptjsx")

    assert (
        spec["parser_entrypoint"]
        == "src/platform_context_graph/parsers/languages/typescriptjsx.py"
    )
