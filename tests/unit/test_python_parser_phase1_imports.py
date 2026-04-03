"""Phase 1 import tests for the Python parser pilot move."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.parsers.capabilities import load_language_capability_specs
from platform_context_graph.parsers.languages.python import (
    PythonTreeSitterParser,
    pre_scan_python,
)
from platform_context_graph.tools.languages.python import (
    PythonTreeSitterParser as LegacyPythonTreeSitterParser,
)
from platform_context_graph.tools.languages.python import (
    pre_scan_python as legacy_pre_scan_python,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_new_python_parser_module_exports_public_api() -> None:
    """The new parser module should expose the Python parser public API."""

    assert PythonTreeSitterParser is not None
    assert callable(pre_scan_python)


def test_legacy_python_parser_module_reexports_new_public_api() -> None:
    """The legacy tools path should keep working during the transition."""

    assert LegacyPythonTreeSitterParser is PythonTreeSitterParser
    assert legacy_pre_scan_python is pre_scan_python


def test_python_capability_spec_points_to_new_parser_entrypoint() -> None:
    """The canonical Python capability spec should reference the new parser path."""

    specs = load_language_capability_specs(REPO_ROOT)
    python_spec = next(spec for spec in specs if spec["language"] == "python")

    assert (
        python_spec["parser_entrypoint"]
        == "src/platform_context_graph/parsers/languages/python.py"
    )
