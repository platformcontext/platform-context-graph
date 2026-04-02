"""Phase 1 import tests for the TypeScript parser pilot move."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.parsers.capabilities import load_language_capability_specs
from platform_context_graph.tools.languages.typescript import (
    TypescriptTreeSitterParser as LegacyTypescriptTreeSitterParser,
)
from platform_context_graph.parsers.languages.typescript import (
    TypescriptTreeSitterParser,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_new_typescript_parser_module_exports_public_api() -> None:
    """The new parser module should expose the TypeScript parser public API."""

    assert TypescriptTreeSitterParser is not None


def test_legacy_typescript_parser_module_reexports_new_public_api() -> None:
    """The legacy tools path should keep working during the transition."""

    assert LegacyTypescriptTreeSitterParser is TypescriptTreeSitterParser


def test_typescript_capability_spec_points_to_new_parser_entrypoint() -> None:
    """The canonical TypeScript capability spec should reference the new parser path."""

    specs = load_language_capability_specs(REPO_ROOT)
    typescript_spec = next(spec for spec in specs if spec["language"] == "typescript")

    assert (
        typescript_spec["parser_entrypoint"]
        == "src/platform_context_graph/parsers/languages/typescript.py"
    )
