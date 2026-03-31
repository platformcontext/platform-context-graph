"""Unit tests for the api-node-boats e2e orchestrator."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "run_api_node_boats_e2e.py"


def _load_module():
    """Load the e2e orchestrator module from disk."""

    spec = importlib.util.spec_from_file_location("run_api_node_boats_e2e", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("run_api_node_boats_e2e", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["run_api_node_boats_e2e"] = module
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> None:
    """Run one git command in a temporary repository."""

    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(path: Path) -> None:
    """Create one tiny git repository."""

    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.com")
    (path / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")


def test_prepare_workspace_creates_disposable_working_copies(tmp_path: Path) -> None:
    """Workspace preparation should create one disposable repo per manifest entry."""

    module = _load_module()
    services_root = tmp_path / "services"
    stacks_root = tmp_path / "terraform-stacks"
    _init_repo(services_root / "api-node-boats")
    _init_repo(stacks_root / "terraform-stack-node10")

    manifest = module.LocalHarnessManifest(
        repos=(
            module.RepositorySpec(
                name="api-node-boats",
                root="services",
                required=True,
                clone_url=None,
            ),
            module.RepositorySpec(
                name="terraform-stack-node10",
                root="terraform-stacks",
                required=True,
                clone_url=None,
            ),
        )
    )

    session = module.prepare_workspace(
        manifest=manifest,
        scratch_root=tmp_path / "scratch",
        root_paths={
            "services": services_root,
            "terraform-stacks": stacks_root,
        },
    )

    assert (session.workspace_root / "api-node-boats" / ".git").is_dir()
    assert (session.workspace_root / "terraform-stack-node10" / ".git").is_dir()
    assert set(session.working_copies) == {"api-node-boats", "terraform-stack-node10"}


def test_prepare_workspace_auto_clones_missing_required_repositories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing required repos should be cloned before disposable copies are made."""

    module = _load_module()
    services_root = tmp_path / "services"
    services_root.mkdir()
    cloned_paths: list[Path] = []

    def fake_ensure_local_repository(*, name: str, root_path: Path, clone_url: str):
        repo_path = root_path / name
        _init_repo(repo_path)
        cloned_paths.append(repo_path)
        return module.clone_support.LocalRepositoryResult(path=repo_path, cloned=True)

    monkeypatch.setattr(module.clone_support, "ensure_local_repository", fake_ensure_local_repository)

    manifest = module.LocalHarnessManifest(
        repos=(
            module.RepositorySpec(
                name="configd",
                root="services",
                required=True,
                clone_url="https://github.com/example/configd.git",
            ),
        )
    )

    session = module.prepare_workspace(
        manifest=manifest,
        scratch_root=tmp_path / "scratch",
        root_paths={"services": services_root},
    )

    assert cloned_paths == [services_root / "configd"]
    assert (session.workspace_root / "configd" / ".git").is_dir()


def test_default_root_paths_follow_expected_repo_layout(tmp_path: Path) -> None:
    """Default local roots should point at the expected repo buckets."""

    module = _load_module()

    roots = module.default_root_paths(tmp_path)

    assert roots["services"] == tmp_path / "repos" / "services"
    assert roots["terraform-stacks"] == tmp_path / "repos" / "terraform-stacks"
    assert roots["terraform-modules"] == tmp_path / "repos" / "terraform-modules"
    assert roots["mobius"] == tmp_path / "repos" / "mobius"


def test_prepare_workspace_from_manifest_path_uses_local_manifest_contract(
    tmp_path: Path,
) -> None:
    """The orchestrator should accept the local-only manifest format directly."""

    module = _load_module()
    services_root = tmp_path / "repos" / "services"
    stacks_root = tmp_path / "repos" / "terraform-stacks"
    _init_repo(services_root / "api-node-boats")
    _init_repo(stacks_root / "terraform-stack-node10")
    manifest_path = tmp_path / "api-node-boats-ecosystem.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "subject_repository: api-node-boats",
                "repos:",
                "  - name: api-node-boats",
                "    root: services",
                "    required: true",
                "  - name: terraform-stack-node10",
                "    root: terraform-stacks",
                "    required: true",
                "bootstrap_assertions:",
                "  blocking:",
                "    - kind: story",
                "scan_mutations:",
                "  - repo: terraform-stack-node10",
                "    file: shared/ecs.tf",
                "scan_assertions:",
                "  blocking:",
                "    - kind: repo_reprocessed",
                "      repo: terraform-stack-node10",
                "",
            ]
        ),
        encoding="utf-8",
    )

    session = module.prepare_workspace_from_manifest_path(
        manifest_path=manifest_path,
        scratch_root=tmp_path / "scratch",
        home_dir=tmp_path,
    )

    assert (session.workspace_root / "api-node-boats" / ".git").is_dir()
    assert (session.workspace_root / "terraform-stack-node10" / ".git").is_dir()
