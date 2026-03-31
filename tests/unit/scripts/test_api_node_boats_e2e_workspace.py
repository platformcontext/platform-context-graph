"""Unit tests for the api-node-boats e2e workspace planner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "api_node_boats_e2e_workspace.py"


def _load_module():
    """Load the workspace planner module from disk."""

    spec = importlib.util.spec_from_file_location(
        "api_node_boats_e2e_workspace", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("api_node_boats_e2e_workspace", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["api_node_boats_e2e_workspace"] = module
    spec.loader.exec_module(module)
    return module


def test_plan_workspace_groups_repositories_by_clone_root(tmp_path: Path) -> None:
    """The workspace plan should resolve repositories under their declared roots."""

    module = _load_module()
    services_root = tmp_path / "services"
    stacks_root = tmp_path / "terraform-stacks"
    services_root.mkdir()
    stacks_root.mkdir()
    (services_root / "api-node-boats").mkdir()
    (stacks_root / "terraform-stack-node10").mkdir()

    manifest = module.LocalWorkspaceManifest(
        repos=(
            module.RepositoryPlan(name="api-node-boats", root="services", required=True),
            module.RepositoryPlan(
                name="terraform-stack-node10",
                root="terraform-stacks",
                required=True,
            ),
        )
    )

    plan = module.plan_workspace(
        manifest,
        root_paths={
            "services": services_root,
            "terraform-stacks": stacks_root,
        },
    )

    assert [repo.name for repo in plan.present_repositories] == [
        "api-node-boats",
        "terraform-stack-node10",
    ]
    assert plan.missing_required_repositories == ()
    assert plan.missing_optional_repositories == ()


def test_plan_workspace_reports_missing_required_repositories(tmp_path: Path) -> None:
    """Missing required repositories should be surfaced explicitly."""

    module = _load_module()
    services_root = tmp_path / "services"
    services_root.mkdir()

    manifest = module.LocalWorkspaceManifest(
        repos=(
            module.RepositoryPlan(name="api-node-boats", root="services", required=True),
            module.RepositoryPlan(name="configd", root="services", required=True),
        )
    )

    plan = module.plan_workspace(
        manifest,
        root_paths={"services": services_root},
    )

    assert [repo.name for repo in plan.missing_required_repositories] == [
        "api-node-boats",
        "configd",
    ]


def test_plan_workspace_leaves_optional_missing_repositories_as_diagnostics(
    tmp_path: Path,
) -> None:
    """Optional repositories should not be promoted to required failures."""

    module = _load_module()
    services_root = tmp_path / "services"
    services_root.mkdir()
    (services_root / "api-node-boats").mkdir()

    manifest = module.LocalWorkspaceManifest(
        repos=(
            module.RepositoryPlan(name="api-node-boats", root="services", required=True),
            module.RepositoryPlan(name="article-indexer", root="services", required=False),
        )
    )

    plan = module.plan_workspace(
        manifest,
        root_paths={"services": services_root},
    )

    assert [repo.name for repo in plan.present_repositories] == ["api-node-boats"]
    assert plan.missing_required_repositories == ()
    assert [repo.name for repo in plan.missing_optional_repositories] == [
        "article-indexer"
    ]
