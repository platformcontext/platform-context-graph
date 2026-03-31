"""Orchestrate the local api-node-boats filesystem-backed e2e workspace."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import json
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


def write_workspace_session_artifact(
    session: WorkspaceSession, output_path: Path
) -> None:
    """Persist one workspace-session artifact for shell wrappers and tests."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "workspace_root": str(session.workspace_root),
                "working_copies": {
                    name: str(path) for name, path in sorted(session.working_copies.items())
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the local harness helper."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare-workspace",
        help="Create one disposable workspace from the local ecosystem manifest.",
    )
    prepare_parser.add_argument("--manifest-path", required=True)
    prepare_parser.add_argument("--scratch-root", required=True)
    prepare_parser.add_argument("--output-json", required=True)
    prepare_parser.add_argument("--home-dir", default=str(Path.home()))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one orchestrator command."""

    args = parse_args(argv)
    if args.command != "prepare-workspace":
        raise ValueError(f"Unsupported command: {args.command}")
    session = prepare_workspace_from_manifest_path(
        manifest_path=Path(args.manifest_path).expanduser(),
        scratch_root=Path(args.scratch_root).expanduser(),
        home_dir=Path(args.home_dir).expanduser(),
    )
    write_workspace_session_artifact(
        session,
        Path(args.output_json).expanduser(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
