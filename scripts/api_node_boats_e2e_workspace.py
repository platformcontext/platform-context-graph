"""Workspace planning helpers for the local api-node-boats e2e harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepositoryPlan:
    """One repository that should exist in the local ecosystem workspace."""

    name: str
    root: str
    required: bool


@dataclass(frozen=True)
class LocalWorkspaceManifest:
    """Minimal workspace-facing manifest contract."""

    repos: tuple[RepositoryPlan, ...]


@dataclass(frozen=True)
class PresentRepository:
    """One repository resolved on local disk."""

    name: str
    root: str
    path: Path


@dataclass(frozen=True)
class WorkspacePlan:
    """Resolution results for the local workspace corpus."""

    present_repositories: tuple[PresentRepository, ...]
    missing_required_repositories: tuple[RepositoryPlan, ...]
    missing_optional_repositories: tuple[RepositoryPlan, ...]


def plan_workspace(
    manifest: LocalWorkspaceManifest,
    *,
    root_paths: dict[str, Path],
) -> WorkspacePlan:
    """Resolve one local workspace plan from configured root paths."""

    present: list[PresentRepository] = []
    missing_required: list[RepositoryPlan] = []
    missing_optional: list[RepositoryPlan] = []

    for repository in manifest.repos:
        root_path = root_paths[repository.root]
        resolved_path = root_path / repository.name
        if resolved_path.exists():
            present.append(
                PresentRepository(
                    name=repository.name,
                    root=repository.root,
                    path=resolved_path,
                )
            )
            continue
        if repository.required:
            missing_required.append(repository)
        else:
            missing_optional.append(repository)

    return WorkspacePlan(
        present_repositories=tuple(present),
        missing_required_repositories=tuple(missing_required),
        missing_optional_repositories=tuple(missing_optional),
    )
