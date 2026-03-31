"""Disposable git helpers for the api-node-boats local e2e harness."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(cwd: Path | None, *args: str) -> str:
    """Run one git command and return stdout."""

    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def create_bare_remote(*, source_repo: Path, bare_root: Path) -> Path:
    """Mirror one local repository into a disposable bare remote."""

    bare_root.mkdir(parents=True, exist_ok=True)
    bare_repo = bare_root / f"{source_repo.name}.git"
    _run_git(None, "clone", "--bare", str(source_repo), str(bare_repo))
    return bare_repo


def create_disposable_working_copy(*, bare_repo: Path, working_root: Path) -> Path:
    """Clone one disposable working copy from a disposable bare remote."""

    working_root.mkdir(parents=True, exist_ok=True)
    repo_name = bare_repo.name.removesuffix(".git")
    working_copy = working_root / repo_name
    _run_git(None, "clone", str(bare_repo), str(working_copy))
    _run_git(working_copy, "config", "user.name", "PCG E2E Harness")
    _run_git(working_copy, "config", "user.email", "pcg-e2e@example.com")
    return working_copy


def commit_and_push_change(
    *,
    repo_path: Path,
    relative_path: Path,
    content: str,
    message: str,
) -> str:
    """Write one file change, commit it, and push it to the disposable upstream."""

    target_path = repo_path / relative_path
    target_path.write_text(content, encoding="utf-8")
    _run_git(repo_path, "add", str(relative_path))
    _run_git(repo_path, "commit", "-m", message)
    _run_git(repo_path, "push", "origin", "HEAD")
    return _run_git(repo_path, "rev-parse", "HEAD")
