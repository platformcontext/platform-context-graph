"""Unit tests for disposable git runtime helpers."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "api_node_boats_e2e_git_runtime.py"


def _load_module():
    """Load the git runtime helper module from disk."""

    spec = importlib.util.spec_from_file_location(
        "api_node_boats_e2e_git_runtime", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("api_node_boats_e2e_git_runtime", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["api_node_boats_e2e_git_runtime"] = module
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


def _init_repository(path: Path) -> None:
    """Create one tiny git repository with an initial commit."""

    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.com")
    (path / "README.md").write_text("# temp repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")


def test_create_bare_remote_from_local_repository(tmp_path: Path) -> None:
    """The helper should mirror a local repository into one bare upstream."""

    module = _load_module()
    source_repo = tmp_path / "source"
    _init_repository(source_repo)
    bare_root = tmp_path / "bare"

    bare_repo = module.create_bare_remote(
        source_repo=source_repo,
        bare_root=bare_root,
    )

    assert bare_repo.is_dir()
    assert (bare_repo / "HEAD").is_file()


def test_create_disposable_working_copy_tracks_bare_remote(tmp_path: Path) -> None:
    """Disposable working copies should clone from the bare remote."""

    module = _load_module()
    source_repo = tmp_path / "source"
    _init_repository(source_repo)
    bare_repo = module.create_bare_remote(
        source_repo=source_repo,
        bare_root=tmp_path / "bare",
    )

    working_copy = module.create_disposable_working_copy(
        bare_repo=bare_repo,
        working_root=tmp_path / "working",
    )

    assert (working_copy / ".git").is_dir()
    assert (working_copy / "README.md").is_file()


def test_disposable_working_copy_can_commit_and_push(tmp_path: Path) -> None:
    """Synthetic commits should push back into the disposable upstream."""

    module = _load_module()
    source_repo = tmp_path / "source"
    _init_repository(source_repo)
    bare_repo = module.create_bare_remote(
        source_repo=source_repo,
        bare_root=tmp_path / "bare",
    )
    working_copy = module.create_disposable_working_copy(
        bare_repo=bare_repo,
        working_root=tmp_path / "working",
    )

    pushed_commit = module.commit_and_push_change(
        repo_path=working_copy,
        relative_path=Path("README.md"),
        content="# changed\n",
        message="synthetic test change",
    )

    assert pushed_commit
    clone_path = tmp_path / "verification"
    subprocess.run(
        ["git", "clone", str(bare_repo), str(clone_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (clone_path / "README.md").read_text(encoding="utf-8") == "# changed\n"
