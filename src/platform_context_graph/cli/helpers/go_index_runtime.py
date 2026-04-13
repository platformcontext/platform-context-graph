"""Launch the Go-owned bootstrap index runtime for local CLI indexing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable

from ..config_manager import load_config
from ...paths import get_app_home


def _repo_root() -> Path:
    """Return the repository root for this checkout."""

    return Path(__file__).resolve().parents[4]


def _state_directory_key(
    root_path: Path,
    selected_repositories: Iterable[Path] | None = None,
) -> str:
    """Return a stable state-directory key for one local index target."""

    normalized_root = str(root_path.resolve())
    normalized_repositories = sorted(
        str(repo_path.resolve()) for repo_path in (selected_repositories or [])
    )
    payload = "\n".join([normalized_root, *normalized_repositories]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _selected_repository_rules(
    root_path: Path,
    selected_repositories: Iterable[Path] | None = None,
) -> list[dict[str, str]]:
    """Return exact filesystem selection rules relative to one root path."""

    if not selected_repositories:
        return []

    resolved_root = root_path.resolve()
    rules: list[dict[str, str]] = []
    for repo_path in selected_repositories:
        resolved_repo = repo_path.resolve()
        if resolved_repo == resolved_root:
            rules.append({"kind": "exact", "value": "."})
            continue
        relative_path = resolved_repo.relative_to(resolved_root)
        rules.append(
            {"kind": "exact", "value": relative_path.as_posix().strip("/")}
        )
    return rules


def build_go_bootstrap_index_env(
    root_path: Path,
    *,
    selected_repositories: Iterable[Path] | None = None,
    force: bool = False,
    is_dependency: bool = False,
    package_name: str | None = None,
    language: str | None = None,
) -> dict[str, str]:
    """Build the effective environment for a Go bootstrap-index run."""

    base_env = {key: str(value) for key, value in load_config().items()}
    base_env.update(os.environ)

    state_key = _state_directory_key(root_path, selected_repositories)
    state_dir = get_app_home() / "state" / "go-bootstrap-index" / state_key
    if force and state_dir.exists():
        shutil.rmtree(state_dir)
    repos_dir = state_dir / "repos"
    repos_dir.mkdir(parents=True, exist_ok=True)

    base_env["PCG_REPO_SOURCE_MODE"] = "filesystem"
    base_env["PCG_FILESYSTEM_ROOT"] = str(root_path.resolve())
    base_env["PCG_FILESYSTEM_DIRECT"] = "true"
    base_env["PCG_REPOS_DIR"] = str(repos_dir)

    repository_rules = _selected_repository_rules(root_path, selected_repositories)
    if repository_rules:
        base_env["PCG_REPOSITORY_RULES_JSON"] = json.dumps(repository_rules)
    else:
        base_env.pop("PCG_REPOSITORY_RULES_JSON", None)

    if is_dependency:
        base_env["PCG_BOOTSTRAP_IS_DEPENDENCY"] = "true"
        if package_name:
            base_env["PCG_BOOTSTRAP_PACKAGE_NAME"] = package_name
        else:
            base_env.pop("PCG_BOOTSTRAP_PACKAGE_NAME", None)
        if language:
            base_env["PCG_BOOTSTRAP_PACKAGE_LANGUAGE"] = language
        else:
            base_env.pop("PCG_BOOTSTRAP_PACKAGE_LANGUAGE", None)
    else:
        base_env.pop("PCG_BOOTSTRAP_IS_DEPENDENCY", None)
        base_env.pop("PCG_BOOTSTRAP_PACKAGE_NAME", None)
        base_env.pop("PCG_BOOTSTRAP_PACKAGE_LANGUAGE", None)

    return base_env


def resolve_go_bootstrap_index_command() -> tuple[list[str], Path | None]:
    """Resolve the Go bootstrap-index runtime command."""

    configured_binary = os.getenv("PCG_BOOTSTRAP_INDEX_BIN")
    if configured_binary:
        return [configured_binary], None

    installed_binary = shutil.which("pcg-bootstrap-index")
    if installed_binary:
        return [installed_binary], None

    repo_root = _repo_root()
    go_root = repo_root / "go"
    bootstrap_entrypoint = go_root / "cmd" / "bootstrap-index" / "main.go"
    if (go_root / "go.mod").exists() and bootstrap_entrypoint.exists():
        return ["go", "run", "./cmd/bootstrap-index"], go_root

    raise RuntimeError(
        "Could not resolve the Go bootstrap-index runtime. "
        "Install /usr/local/bin/pcg-bootstrap-index or set PCG_BOOTSTRAP_INDEX_BIN."
    )


def run_go_bootstrap_index(
    root_path: Path,
    *,
    selected_repositories: Iterable[Path] | None = None,
    force: bool = False,
    is_dependency: bool = False,
    package_name: str | None = None,
    language: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the Go bootstrap-index runtime for one local root path."""

    command, cwd = resolve_go_bootstrap_index_command()
    env = build_go_bootstrap_index_env(
        root_path,
        selected_repositories=selected_repositories,
        force=force,
        is_dependency=is_dependency,
        package_name=package_name,
        language=language,
    )
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    details = stderr or stdout or f"exit code {result.returncode}"
    raise RuntimeError(f"Go bootstrap-index failed: {details}")


__all__ = [
    "build_go_bootstrap_index_env",
    "resolve_go_bootstrap_index_command",
    "run_go_bootstrap_index",
]
