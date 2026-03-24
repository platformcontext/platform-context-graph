"""Unit tests for the templated repo inventory script."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "templated_repo_inventory.py"


def _load_script_module(module_name: str) -> ModuleType:
    """Load the CLI script as a module under a test-specific name."""

    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.path.insert(0, str(REPO_ROOT))
    spec.loader.exec_module(module)
    return module


def test_classify_helm_template_yaml_prefers_go_template_bucket() -> None:
    """Helm template YAML should land in the Go-template bucket."""

    module = _load_script_module("templated_repo_inventory_helm")

    classification = module.classify_file(
        root_family="helm_argo",
        relative_path=Path("chart/templates/statefulset.yaml"),
        content=(
            "{{- if .Values.repoSync.enabled }}\n"
            "kind: StatefulSet\n"
            "metadata:\n"
            '  name: {{ include "pcg.fullname" . }}\n'
            "{{- end }}\n"
        ),
    )

    assert classification.bucket == "go_template_yaml"
    assert classification.ambiguous is False
    assert classification.dialects == ("go_template",)
    assert classification.renderability_hint == "context_required"


def test_classify_ansible_yaml_prefers_jinja_bucket() -> None:
    """Ansible-style YAML with template expressions should map to Jinja."""

    module = _load_script_module("templated_repo_inventory_ansible")

    classification = module.classify_file(
        root_family="ansible_jinja",
        relative_path=Path("deploy.yml"),
        content='hosts: "{{ env | default(\'qa\') }}"\n',
    )

    assert classification.bucket == "jinja_yaml"
    assert classification.ambiguous is False
    assert classification.dialects == ("jinja",)
    assert classification.renderability_hint == "context_required"


def test_classify_plain_yaml_in_helm_root_stays_plain() -> None:
    """Helm-family roots should not coerce ordinary YAML into templated YAML."""

    module = _load_script_module("templated_repo_inventory_plain_helm")

    classification = module.classify_file(
        root_family="helm_argo",
        relative_path=Path("argocd/base/function.yaml"),
        content=(
            "# Verify all required fields exist before installation.\n"
            "apiVersion: pkg.crossplane.io/v1\n"
            "kind: Function\n"
        ),
    )

    assert classification.bucket == "plain_yaml"
    assert classification.dialects == ()
    assert classification.marker_count == 0
    assert classification.renderability_hint == "raw_only"


def test_classify_dockerfile_is_a_raw_ingest_candidate() -> None:
    """Plain Dockerfiles should be surfaced as raw-ingest gaps."""

    module = _load_script_module("templated_repo_inventory_dockerfile")

    classification = module.classify_file(
        root_family="generic",
        relative_path=Path("Dockerfile"),
        content="FROM alpine:3.20\nRUN apk add --no-cache bash\n",
    )

    assert classification.bucket == "plain_text"
    assert classification.artifact_type == "dockerfile"
    assert classification.raw_ingest_candidate is True
    assert classification.iac_relevant is True


def test_classify_terraform_hcl_splits_plain_and_templated() -> None:
    """Terraform HCL should separate plain files from templated ones."""

    module = _load_script_module("templated_repo_inventory_terraform")

    plain = module.classify_file(
        root_family="terraform",
        relative_path=Path("modules/example/main.tf"),
        content='resource "aws_s3_bucket" "this" {}\n',
    )
    templated = module.classify_file(
        root_family="terraform",
        relative_path=Path("modules/example/main.tf"),
        content=(
            'resource "aws_s3_bucket" "this" {\n'
            '  bucket = "${var.bucket_name}"\n'
            "}\n"
        ),
    )

    assert plain.bucket == "terraform_hcl"
    assert plain.dialects == ()
    assert plain.renderability_hint == "raw_only"

    assert templated.bucket == "terraform_hcl_templated"
    assert templated.ambiguous is False
    assert templated.dialects == ("terraform_template",)
    assert templated.renderability_hint == "context_required"


def test_classify_mixed_yaml_reports_unknown_templated() -> None:
    """Mixed dialect markers should stay ambiguous instead of forcing a guess."""

    module = _load_script_module("templated_repo_inventory_ambiguous")

    classification = module.classify_file(
        root_family="generic",
        relative_path=Path("mixed.yaml"),
        content=(
            "kind: ConfigMap\n"
            "metadata:\n"
            "  name: {{ repo_name }}\n"
            "{% if enabled %}\n"
            "data:\n"
            "  key: value\n"
            "{% endif %}\n"
        ),
    )

    assert classification.bucket == "unknown_templated"
    assert classification.ambiguous is True
    assert classification.dialects == ("go_template", "jinja")


def test_exclusion_reason_skips_generated_paths_by_default() -> None:
    """Generated directories should be excluded unless explicitly included."""

    module = _load_script_module("templated_repo_inventory_exclusions")

    assert module.exclusion_reason(
        Path(".terraform/modules/example/main.tf"),
        include_generated=False,
    ) == ".terraform"
    assert module.exclusion_reason(
        Path(".worktrees/feature/chart/templates/deployment.yaml"),
        include_generated=False,
    ) == ".worktrees"
    assert module.exclusion_reason(
        Path("chart/templates/deployment.yaml"),
        include_generated=False,
    ) is None


def test_scan_root_summarizes_buckets_examples_and_ambiguity(tmp_path: Path) -> None:
    """Scanning a root should keep authored examples and track exclusions."""

    module = _load_script_module("templated_repo_inventory_scan")

    root = tmp_path / "iac-eks-pcg"
    (root / "chart" / "templates").mkdir(parents=True)
    (root / ".terraform" / "modules" / "example").mkdir(parents=True)
    (root / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (root / "values.yaml").write_text("replicas: 1\n", encoding="utf-8")
    (root / "chart" / "templates" / "statefulset.yaml").write_text(
        (
            "{{- if .Values.repoSync.enabled }}\n"
            "kind: StatefulSet\n"
            "{{- end }}\n"
        ),
        encoding="utf-8",
    )
    (root / "chart" / "templates" / "_helpers.tpl").write_text(
        '{{- define "pcg.fullname" -}}pcg{{- end -}}\n',
        encoding="utf-8",
    )
    (root / "ambiguous.yaml").write_text(
        "name: {{ repo_name }}\n{% if enabled %}\nkey: value\n{% endif %}\n",
        encoding="utf-8",
    )
    (root / ".terraform" / "modules" / "example" / "main.tf").write_text(
        'resource "aws_s3_bucket" "this" {}\n',
        encoding="utf-8",
    )

    inventory = module.scan_root(
        module.ScanRoot(name="iac-eks-pcg", path=root, family="helm_argo"),
        max_examples=3,
        include_generated=False,
    )

    assert inventory.buckets["plain_yaml"] == 1
    assert inventory.buckets["plain_text"] == 1
    assert inventory.buckets["go_template_yaml"] == 1
    assert inventory.buckets["helm_helper_tpl"] == 1
    assert inventory.buckets["unknown_templated"] == 1
    assert inventory.raw_ingest_gap_files == 2
    assert inventory.iac_relevant_files == 5
    assert inventory.artifact_types["dockerfile"] == 1
    assert inventory.excluded_path_counts[".terraform"] == 1
    assert [item.relative_path for item in inventory.ambiguous_files] == [
        Path("ambiguous.yaml")
    ]
    assert [item.relative_path for item in inventory.examples] == [
        Path("Dockerfile"),
        Path("chart/templates/statefulset.yaml"),
        Path("chart/templates/_helpers.tpl"),
    ]
    assert [item.relative_path for item in inventory.raw_ingest_examples] == [
        Path("chart/templates/_helpers.tpl"),
        Path("Dockerfile"),
    ]


def test_main_writes_json_report(tmp_path: Path) -> None:
    """`main` should emit a compact JSON report with stable top-level keys."""

    module = _load_script_module("templated_repo_inventory_main")

    root = tmp_path / "bg-dagster"
    root.mkdir()
    (root / "asset.yaml").write_text(
        'asset_group: "{{ env }}"\n',
        encoding="utf-8",
    )
    json_path = tmp_path / "report.json"

    exit_code = module.main(
        [
            "--root",
            str(root),
            "--family",
            "ansible_jinja",
            "--json-out",
            str(json_path),
            "--max-examples",
            "2",
        ]
    )

    assert exit_code == 0

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert list(report) == ["roots"]
    assert report["roots"][0]["name"] == "bg-dagster"
    assert sorted(report["roots"][0]) == [
        "ambiguous_files",
        "artifact_types",
        "buckets",
        "examples",
        "excluded_path_counts",
        "family",
        "iac_examples",
        "iac_relevant_files",
        "name",
        "path",
        "raw_ingest_examples",
        "raw_ingest_gap_files",
    ]


def test_main_returns_one_when_inventory_finds_ambiguity(tmp_path: Path) -> None:
    """`main` should fail closed when the inventory contains ambiguous files."""

    module = _load_script_module("templated_repo_inventory_ambiguous_main")

    root = tmp_path / "generic-root"
    root.mkdir()
    (root / "mixed.yaml").write_text(
        "name: {{ repo_name }}\n{% if enabled %}\nkey: value\n{% endif %}\n",
        encoding="utf-8",
    )
    json_path = tmp_path / "report.json"

    exit_code = module.main(
        [
            "--root",
            str(root),
            "--family",
            "generic",
            "--json-out",
            str(json_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["roots"][0]["ambiguous_files"][0]["relative_path"] == "mixed.yaml"


def test_scan_root_skips_read_errors_and_records_them(tmp_path: Path) -> None:
    """Unreadable or missing files should not abort the inventory scan."""

    module = _load_script_module("templated_repo_inventory_read_error")

    root = tmp_path / "ansible-automate"
    root.mkdir()
    missing_path = root / "broken.yml"

    inventory = module.scan_root(
        module.ScanRoot(name="ansible-automate", path=root, family="ansible_jinja"),
        max_examples=2,
        include_generated=False,
        candidate_files=(missing_path,),
    )

    assert inventory.buckets["jinja_yaml"] == 0
    assert inventory.examples == ()
    assert inventory.excluded_path_counts["__read_error__"] == 1


def test_script_runs_as_standalone_entrypoint() -> None:
    """The inventory script should be runnable directly by file path."""

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "Inventory authored templated files" in result.stdout
