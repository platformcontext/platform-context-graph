"""Unit tests for evidence-bearing scan mutations."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "api_node_boats_e2e_mutations.py"


def _load_module():
    """Load the mutation helper module from disk."""

    spec = importlib.util.spec_from_file_location(
        "api_node_boats_e2e_mutations", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("api_node_boats_e2e_mutations", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["api_node_boats_e2e_mutations"] = module
    spec.loader.exec_module(module)
    return module


def test_apply_workflow_mutation_updates_manual_deploy_workflow(tmp_path: Path) -> None:
    """Workflow mutation should add a parseable dispatch input marker."""

    module = _load_module()
    workflow_path = tmp_path / "manual-deploy.yml"
    workflow_path.write_text(
        "\n".join(
            [
                "name: manual deploy",
                "on:",
                "  workflow_dispatch:",
                "    inputs:",
                "      environment:",
                "        required: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    module.apply_workflow_mutation(workflow_path)

    content = workflow_path.read_text(encoding="utf-8")
    assert "pcg_e2e_marker" in content
    assert "default: scan-phase" in content


def test_apply_terraform_mutation_updates_api_node_boats_ecs_block(tmp_path: Path) -> None:
    """Terraform mutation should change a parseable field inside the boats module."""

    module = _load_module()
    terraform_path = tmp_path / "ecs.tf"
    terraform_path.write_text(
        "\n".join(
            [
                'module "api_node_boats" {',
                '  name = "api-node-boats"',
                "  create_deploy = false",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    module.apply_terraform_mutation(terraform_path)

    content = terraform_path.read_text(encoding="utf-8")
    assert 'pcg_e2e_marker = "scan-phase"' in content


def test_mutations_are_idempotent_for_repeat_runs(tmp_path: Path) -> None:
    """Repeat runs should not duplicate mutation lines."""

    module = _load_module()
    workflow_path = tmp_path / "manual-deploy.yml"
    workflow_path.write_text(
        "\n".join(
            [
                "name: manual deploy",
                "on:",
                "  workflow_dispatch:",
                "    inputs:",
                "      environment:",
                "        required: true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    terraform_path = tmp_path / "ecs.tf"
    terraform_path.write_text(
        "\n".join(
            [
                'module "api_node_boats" {',
                '  name = "api-node-boats"',
                "  create_deploy = false",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    module.apply_workflow_mutation(workflow_path)
    module.apply_workflow_mutation(workflow_path)
    module.apply_terraform_mutation(terraform_path)
    module.apply_terraform_mutation(terraform_path)

    assert workflow_path.read_text(encoding="utf-8").count("pcg_e2e_marker") == 1
    assert terraform_path.read_text(encoding="utf-8").count("pcg_e2e_marker") == 1
