"""Unit tests for the local-only api-node-boats e2e manifest loader."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT / "scripts" / "api_node_boats_e2e_manifest.py"
)


def _load_module():
    """Load the manifest helper module from disk."""

    spec = importlib.util.spec_from_file_location(
        "api_node_boats_e2e_manifest", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("api_node_boats_e2e_manifest", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["api_node_boats_e2e_manifest"] = module
    spec.loader.exec_module(module)
    return module


def test_load_manifest_parses_required_and_optional_repositories(
    tmp_path: Path,
) -> None:
    """The loader should preserve required and optional repository entries."""

    module = _load_module()
    manifest_path = tmp_path / "ecosystem.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "subject_repository: api-node-boats",
                "repos:",
                "  - name: api-node-boats",
                "    root: services",
                "    required: true",
                "    clone_url: https://github.com/example/api-node-boats.git",
                "  - name: configd",
                "    root: services",
                "    required: false",
                "    clone_url: https://github.com/example/configd.git",
                "bootstrap_assertions:",
                "  blocking:",
                "    - kind: provisioned_by",
                "      expected_repo: terraform-stack-node10",
                "scan_mutations:",
                "  - repo: api-node-provisioning-indexer",
                "    file: .github/workflows/manual-deploy.yml",
                "scan_assertions:",
                "  blocking:",
                "    - kind: repo_reprocessed",
                "      repo: api-node-provisioning-indexer",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest = module.load_manifest(manifest_path)

    assert manifest.subject_repository == "api-node-boats"
    assert [repo.name for repo in manifest.repos] == ["api-node-boats", "configd"]
    assert manifest.repos[0].required is True
    assert manifest.repos[1].required is False
    assert manifest.repos[0].clone_url == "https://github.com/example/api-node-boats.git"


def test_load_manifest_requires_bootstrap_and_scan_assertions(tmp_path: Path) -> None:
    """The loader should reject manifests missing assertion contracts."""

    module = _load_module()
    manifest_path = tmp_path / "ecosystem.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "subject_repository: api-node-boats",
                "repos:",
                "  - name: api-node-boats",
                "    root: services",
                "    required: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="bootstrap_assertions"):
        module.load_manifest(manifest_path)


def test_load_manifest_requires_scan_mutation_targets(tmp_path: Path) -> None:
    """The loader should reject manifests without scan mutations."""

    module = _load_module()
    manifest_path = tmp_path / "ecosystem.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "subject_repository: api-node-boats",
                "repos:",
                "  - name: api-node-boats",
                "    root: services",
                "    required: true",
                "bootstrap_assertions:",
                "  blocking:",
                "    - kind: api_surface",
                "      expected_version: v3",
                "scan_assertions:",
                "  blocking:",
                "    - kind: repo_reprocessed",
                "      repo: terraform-stack-node10",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="scan_mutations"):
        module.load_manifest(manifest_path)
