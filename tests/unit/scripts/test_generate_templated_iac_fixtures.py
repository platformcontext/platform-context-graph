"""Unit tests for the templated IaC fixture generation script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_templated_iac_fixtures.py"
SUPPORT_PATH = REPO_ROOT / "scripts" / "generate_templated_iac_fixtures_support.py"


def _load_module(path: Path, module_name: str) -> ModuleType:
    """Load a standalone script/support module under a unique test name."""

    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.path.insert(0, str(REPO_ROOT))
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_generate_fixture_corpus_sanitizes_company_markers(tmp_path: Path) -> None:
    """Generated fixtures should keep template syntax while scrubbing real markers."""

    support = _load_module(
        SUPPORT_PATH,
        "generate_templated_iac_fixtures_support_test",
    )

    source_root = tmp_path / "source"
    source_root.mkdir()
    helm_source = source_root / "chart" / "templates" / "_helpers.tpl"
    helm_source.parent.mkdir(parents=True)
    helm_source.write_text(
        (
            '{{- define "pcg.fullname" -}}\n'
            'image: boatsgroup.pe.jfrog.io/bg-docker/platformcontextgraph\n'
            "githubOrg: boatsgroup\n"
            "{{- end -}}\n"
        ),
        encoding="utf-8",
    )
    dagster_source = source_root / "assets" / "data_quality.yaml"
    dagster_source.parent.mkdir(parents=True)
    dagster_source.write_text(
        (
            'webhook_url: https://hooks.slack.com/services/T1/B2/secret\n'
            "{% set portals = [\n"
            "  'boats.com',\n"
            "  'yachtworld'\n"
            "] %}\n"
            "checks: {{ portals | tojson }}\n"
        ),
        encoding="utf-8",
    )

    specs = [
        support.FixtureFileSpec(
            source=helm_source,
            target_repo="example-chart",
            target_path="chart/templates/_helpers.tpl",
            family="helm_go_template",
            artifact_type="helm_helper_tpl",
        ),
        support.FixtureFileSpec(
            source=dagster_source,
            target_repo="example-dagster",
            target_path="assets/data_quality.yaml",
            family="dagster_jinja_yaml",
            artifact_type="jinja_yaml",
            transform="dagster_quality",
        ),
    ]

    output_root = tmp_path / "fixtures"
    records = support.generate_fixture_corpus(output_root, specs=specs)

    assert len(records) == 2
    helm_text = (output_root / "example-chart/chart/templates/_helpers.tpl").read_text(
        encoding="utf-8"
    )
    dagster_text = (output_root / "example-dagster/assets/data_quality.yaml").read_text(
        encoding="utf-8"
    )
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    readme = (output_root / "README.md").read_text(encoding="utf-8")

    assert "boatsgroup" not in helm_text
    assert "jfrog.io" not in helm_text
    assert '{{- define "pcg.fullname" -}}' in helm_text
    assert "hooks.slack.com" not in dagster_text
    assert "'portal-alpha'" in dagster_text
    assert "{{ portals | tojson }}" in dagster_text
    assert manifest["repos"] == ["example-chart", "example-dagster"]
    assert "Templated IaC Fixture Corpus" in readme


def test_cli_writes_fixture_output(tmp_path: Path, monkeypatch) -> None:
    """The CLI should delegate to support generation and report the output path."""

    module = _load_module(
        SCRIPT_PATH,
        "generate_templated_iac_fixtures_cli_test",
    )
    called: dict[str, object] = {}

    def fake_generate(output_root: Path):
        called["output_root"] = output_root
        return []

    monkeypatch.setattr(module, "generate_fixture_corpus", fake_generate)

    exit_code = module.main(["--output", str(tmp_path / "fixture-out")])

    assert exit_code == 0
    assert called["output_root"] == tmp_path / "fixture-out"
