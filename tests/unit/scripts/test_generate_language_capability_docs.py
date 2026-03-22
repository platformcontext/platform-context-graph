"""Unit tests for the parser capability doc generation CLI."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_language_capability_docs.py"


def _load_script_module(module_name: str) -> ModuleType:
    """Load the CLI script as a module under a test-specific name."""

    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    spec.loader.exec_module(module)
    return module


def test_main_reports_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main` should surface validation errors on stderr and return failure."""

    module = _load_script_module("generate_language_capability_docs_validation")
    stdout = io.StringIO()
    stderr = io.StringIO()

    monkeypatch.setattr(
        module,
        "_validate_language_capability_specs",
        lambda root: ["spec one", "spec two"],
    )

    exit_code = module.main([], stdout=stdout, stderr=stderr)

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "Parser capability spec validation failed:" in stderr.getvalue()
    assert "- spec one" in stderr.getvalue()
    assert "- spec two" in stderr.getvalue()


def test_main_reports_check_mode_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main --check` should fail when generated docs drift from specs."""

    module = _load_script_module("generate_language_capability_docs_check")
    stdout = io.StringIO()
    stderr = io.StringIO()

    monkeypatch.setattr(module, "_validate_language_capability_specs", lambda root: [])
    monkeypatch.setattr(
        module,
        "_write_generated_language_docs",
        lambda root, check: ["docs/docs/languages/python.md"],
    )

    exit_code = module.main(["--check"], stdout=stdout, stderr=stderr)

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "Generated language docs are out of sync with the YAML specs:" in (
        stderr.getvalue()
    )
    assert "- docs/docs/languages/python.md" in stderr.getvalue()


def test_main_reports_updated_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main` should list regenerated docs on stdout when files change."""

    module = _load_script_module("generate_language_capability_docs_generate")
    stdout = io.StringIO()
    stderr = io.StringIO()

    monkeypatch.setattr(module, "_validate_language_capability_specs", lambda root: [])
    monkeypatch.setattr(
        module,
        "_write_generated_language_docs",
        lambda root, check: ["docs/docs/languages/python.md"],
    )

    exit_code = module.main([], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Updated generated language docs:" in stdout.getvalue()
    assert "- docs/docs/languages/python.md" in stdout.getvalue()
