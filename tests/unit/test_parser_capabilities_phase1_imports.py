"""Phase 1 import tests for the parser capabilities package move."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.parsers.capabilities import (
    load_language_capability_specs,
    render_feature_matrix,
    render_language_doc,
    validate_language_capability_specs,
)
from platform_context_graph.tools.parser_capabilities import (
    load_language_capability_specs as legacy_load_language_capability_specs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_new_parser_capabilities_package_exports_public_api() -> None:
    """The new parser capabilities package should expose the public API."""

    assert callable(load_language_capability_specs)
    assert callable(render_feature_matrix)
    assert callable(render_language_doc)
    assert callable(validate_language_capability_specs)


def test_legacy_parser_capabilities_imports_reexport_new_api() -> None:
    """The legacy tools path should keep working during the transition."""

    assert legacy_load_language_capability_specs is load_language_capability_specs


def test_repo_prefers_specs_under_new_parsers_package() -> None:
    """The repository should read canonical specs from the new parsers path."""

    specs = load_language_capability_specs(REPO_ROOT)

    assert specs
    assert all(
        spec["spec_path"].startswith(
            "src/platform_context_graph/parsers/capabilities/specs/"
        )
        for spec in specs
    )
