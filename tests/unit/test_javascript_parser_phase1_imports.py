"""Phase 1 import compatibility tests for the JavaScript parser package move."""

from pathlib import Path

from platform_context_graph.parsers.languages.javascript import (
    JavascriptTreeSitterParser as NewJavascriptTreeSitterParser,
)
from platform_context_graph.parsers.capabilities import load_language_capability_specs
from platform_context_graph.tools.languages.javascript import (
    JavascriptTreeSitterParser as LegacyJavascriptTreeSitterParser,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_javascript_parser_moves_to_parsers_package() -> None:
    """Expose the JavaScript parser from the new parsers package."""
    assert NewJavascriptTreeSitterParser.__module__ == (
        "platform_context_graph.parsers.languages.javascript_support"
    )


def test_legacy_javascript_parser_reexports_new_parser() -> None:
    """Keep legacy imports working during the Phase 1 package migration."""
    assert LegacyJavascriptTreeSitterParser is NewJavascriptTreeSitterParser


def test_javascript_capability_spec_uses_new_entrypoint() -> None:
    """Point the JavaScript capability spec at the new parser package."""
    specs = load_language_capability_specs(REPO_ROOT)
    spec = next(item for item in specs if item["language"] == "javascript")

    assert (
        spec["parser_entrypoint"]
        == "src/platform_context_graph/parsers/languages/javascript.py"
    )
