"""Unit tests for the language support end-to-end validation CLI."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_language_support_e2e.py"


def _load_script_module(module_name: str) -> ModuleType:
    """Load the CLI script as a module under a test-specific name."""

    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    spec.loader.exec_module(module)
    return module


def test_validate_report_flags_missing_framework_evidence() -> None:
    """Validation should fail when framework evidence is required but missing."""

    module = _load_script_module("validate_language_support_e2e_validate")

    errors = module._validate_report(
        {
            "index_run": {
                "status": "completed",
                "finalization_status": "completed",
            },
            "indexed_file_count": 42,
            "context_framework_summary_present": False,
            "summary_framework_summary_present": False,
            "story_framework_section_present": False,
        },
        require_framework_evidence=True,
    )

    assert "framework evidence was required but context lacked framework_summary" in (
        errors
    )
    assert "framework evidence was required but summary lacked framework_summary" in (
        errors
    )
    assert "framework evidence was required but story lacked Frameworks section" in (
        errors
    )


def test_main_reports_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main --check` should surface validation failures on stderr."""

    module = _load_script_module("validate_language_support_e2e_errors")
    stdout = io.StringIO()
    stderr = io.StringIO()
    report = {
        "repo_name": "portal-react-platform",
        "language": "javascript",
    }

    monkeypatch.setattr(module, "_build_validation_report", lambda args: report)
    monkeypatch.setattr(
        module,
        "_validate_report",
        lambda report, require_framework_evidence: [
            "index run did not complete cleanly"
        ],
    )

    exit_code = module.main(
        [
            "--repo-path",
            "/Users/allen/repos/services/portal-react-platform",
            "--language",
            "javascript",
            "--check",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "Language support validation failed:" in stderr.getvalue()
    assert "- index run did not complete cleanly" in stderr.getvalue()


def test_main_prints_report_when_validation_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`main --check` should print the JSON report when validation passes."""

    module = _load_script_module("validate_language_support_e2e_success")
    stdout = io.StringIO()
    stderr = io.StringIO()
    report = {
        "repo_name": "api-node-platform",
        "language": "typescript",
        "indexed_file_count": 109,
        "index_run": {
            "status": "completed",
            "finalization_status": "completed",
        },
    }

    monkeypatch.setattr(module, "_build_validation_report", lambda args: report)
    monkeypatch.setattr(module, "_validate_report", lambda report, **kwargs: [])

    exit_code = module.main(
        [
            "--repo-path",
            "/Users/allen/repos/services/api-node-platform",
            "--language",
            "typescript",
            "--check",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue()) == report


def test_parse_args_accepts_python_language() -> None:
    """The CLI should expose Python as a graph-backed validation lane."""

    module = _load_script_module("validate_language_support_e2e_python")

    args = module.parse_args(
        [
            "--repo-path",
            "/Users/allen/repos/services/recos-ranker-service",
            "--language",
            "python",
        ]
    )

    assert args.language == "python"
    assert module._LANGUAGE_SUFFIXES["python"] == (".py",)
