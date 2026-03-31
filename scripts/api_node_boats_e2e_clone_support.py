"""Helpers for auto-cloning missing local repositories for the e2e harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class LocalRepositoryResult:
    """One resolved local repository outcome."""

    path: Path
    cloned: bool


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    """Run one clone command."""

    subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def ensure_local_repository(
    *,
    name: str,
    root_path: Path,
    clone_url: str,
) -> LocalRepositoryResult:
    """Ensure one repository exists under the expected local root."""

    target_path = root_path / name
    if target_path.exists():
        return LocalRepositoryResult(path=target_path, cloned=False)

    root_path.mkdir(parents=True, exist_ok=True)
    _run(["gh", "repo", "clone", clone_url, name], cwd=root_path)
    if not target_path.exists():
        raise RuntimeError(f"Repository {name} was not cloned into {target_path}")
    return LocalRepositoryResult(path=target_path, cloned=True)
