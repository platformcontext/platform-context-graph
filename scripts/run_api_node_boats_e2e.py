"""Orchestrate the local api-node-boats filesystem-backed e2e workspace."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_sibling_module(filename: str, module_name: str) -> ModuleType:
    """Load one sibling script module from the scripts directory."""

    module_path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


clone_support = _load_sibling_module(
    "api_node_boats_e2e_clone_support.py",
    "api_node_boats_e2e_clone_support_runtime",
)
git_runtime = _load_sibling_module(
    "api_node_boats_e2e_git_runtime.py",
    "api_node_boats_e2e_git_runtime_runtime",
)
manifest_support = _load_sibling_module(
    "api_node_boats_e2e_manifest.py",
    "api_node_boats_e2e_manifest_runtime",
)


@dataclass(frozen=True)
class RepositorySpec:
    """One repository entry needed for the local harness."""

    name: str
    root: str
    required: bool
    clone_url: str | None


@dataclass(frozen=True)
class LocalHarnessManifest:
    """Subset of manifest data required for workspace preparation."""

    repos: tuple[RepositorySpec, ...]


@dataclass(frozen=True)
class WorkspaceSession:
    """Prepared disposable workspace state."""

    workspace_root: Path
    working_copies: dict[str, Path]


def default_root_paths(home_dir: Path) -> dict[str, Path]:
    """Return the expected local repo roots under one home directory."""

    repos_root = home_dir / "repos"
    return {
        "services": repos_root / "services",
        "terraform-stacks": repos_root / "terraform-stacks",
        "terraform-modules": repos_root / "terraform-modules",
        "mobius": repos_root / "mobius",
        "libs": repos_root / "libs",
        "ansible-automate": repos_root / "ansible-automate",
    }


def prepare_workspace(
    *,
    manifest: LocalHarnessManifest,
    scratch_root: Path,
    root_paths: dict[str, Path],
) -> WorkspaceSession:
    """Create a disposable filesystem workspace from local repos."""

    remotes_root = scratch_root / "remotes"
    workspace_root = scratch_root / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    working_copies: dict[str, Path] = {}
    for repository in manifest.repos:
        local_path = root_paths[repository.root] / repository.name
        if not local_path.exists():
            if repository.clone_url is None:
                raise RuntimeError(
                    f"Missing required clone URL for repository {repository.name}"
                )
            clone_result = clone_support.ensure_local_repository(
                name=repository.name,
                root_path=root_paths[repository.root],
                clone_url=repository.clone_url,
            )
            local_path = clone_result.path
        bare_repo = git_runtime.create_bare_remote(
            source_repo=local_path,
            bare_root=remotes_root,
        )
        working_copy = git_runtime.create_disposable_working_copy(
            bare_repo=bare_repo,
            working_root=workspace_root,
        )
        working_copies[repository.name] = working_copy

    return WorkspaceSession(
        workspace_root=workspace_root,
        working_copies=working_copies,
    )


def prepare_workspace_from_manifest_path(
    *,
    manifest_path: Path,
    scratch_root: Path,
    home_dir: Path,
) -> WorkspaceSession:
    """Load one local-only manifest and prepare its disposable workspace."""

    manifest = manifest_support.load_manifest(manifest_path)
    harness_manifest = LocalHarnessManifest(
        repos=tuple(
            RepositorySpec(
                name=repository.name,
                root=repository.root,
                required=repository.required,
                clone_url=repository.clone_url,
            )
            for repository in manifest.repos
        )
    )
    return prepare_workspace(
        manifest=harness_manifest,
        scratch_root=scratch_root,
        root_paths=default_root_paths(home_dir),
    )
