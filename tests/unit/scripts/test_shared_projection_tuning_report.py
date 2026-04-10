"""Unit tests for the shared projection tuning report script."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "shared_projection_tuning_report.py"
SUPPORT_PATH = REPO_ROOT / "scripts" / "shared_projection_tuning_report_support.py"


def _load_module(path: Path, module_name: str) -> ModuleType:
    """Load one standalone script or support module under a unique name."""

    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.path.insert(0, str(REPO_ROOT))
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_build_default_report_returns_deterministic_recommendation() -> None:
    """The support layer should return one stable default recommendation."""

    module = _load_module(
        SUPPORT_PATH,
        "shared_projection_tuning_report_support_default",
    )

    report = module.build_tuning_report()

    assert report["projection_domains"] == [
        "repo_dependency",
        "workload_dependency",
    ]
    assert [scenario["setting"] for scenario in report["scenarios"]] == [
        "1x1",
        "2x1",
        "4x1",
        "4x2",
    ]
    assert report["recommended"]["setting"] == "4x2"
    assert report["recommended"]["round_count"] == 2


def test_build_default_report_uses_shared_query_module(monkeypatch) -> None:
    """The script support should delegate to the shared query module."""

    module = _load_module(
        SUPPORT_PATH,
        "shared_projection_tuning_report_support_delegate",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "_build_tuning_report",
        lambda **kwargs: captured.update(kwargs) or {"recommended": {"setting": "2x1"}},
    )

    report = module.build_tuning_report(include_platform=True)

    assert report["recommended"]["setting"] == "2x1"
    assert captured["include_platform"] is True


def test_main_prints_json_report(monkeypatch) -> None:
    """The CLI should print JSON when requested."""

    module = _load_module(
        SCRIPT_PATH,
        "shared_projection_tuning_report_cli_json",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(
        module,
        "build_tuning_report",
        lambda **kwargs: {
            "projection_domains": ["repo_dependency"],
            "scenarios": [{"setting": "1x1", "round_count": 4}],
            "recommended": {"setting": "1x1", "round_count": 4},
        },
    )

    exit_code = module.main(["--format", "json"], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["recommended"]["setting"] == "1x1"


def test_main_prints_table_report_and_include_platform(monkeypatch) -> None:
    """The CLI should print a table report and forward include-platform."""

    module = _load_module(
        SCRIPT_PATH,
        "shared_projection_tuning_report_cli_table",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    captured: dict[str, object] = {}

    def _build_report(**kwargs):
        captured.update(kwargs)
        return {
            "projection_domains": [
                "platform_infra",
                "repo_dependency",
                "workload_dependency",
            ],
            "scenarios": [
                {
                    "setting": "4x2",
                    "round_count": 3,
                    "mean_processed_per_round": 12.0,
                }
            ],
            "recommended": {
                "setting": "4x2",
                "round_count": 3,
                "mean_processed_per_round": 12.0,
            },
        }

    monkeypatch.setattr(module, "build_tuning_report", _build_report)

    exit_code = module.main(
        ["--format", "table", "--include-platform"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert captured["include_platform"] is True
    output = stdout.getvalue()
    assert (
        "Projection domains: platform_infra, repo_dependency, workload_dependency"
        in output
    )
    assert "Setting" in output
    assert "4x2" in output
    assert "Recommended setting: 4x2" in output
