"""Unit tests for local repo clone support."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "api_node_boats_e2e_clone_support.py"


def _load_module():
    """Load the clone helper module from disk."""

    spec = importlib.util.spec_from_file_location(
        "api_node_boats_e2e_clone_support", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("api_node_boats_e2e_clone_support", None)
    sys.path.insert(0, str(_REPO_ROOT))
    sys.modules["api_node_boats_e2e_clone_support"] = module
    spec.loader.exec_module(module)
    return module


def test_clone_support_skips_existing_repositories(tmp_path: Path) -> None:
    """Already-present repositories should be left untouched."""

    module = _load_module()
    services_root = tmp_path / "services"
    services_root.mkdir()
    existing_repo = services_root / "api-node-boats"
    existing_repo.mkdir()

    result = module.ensure_local_repository(
        name="api-node-boats",
        root_path=services_root,
        clone_url="https://github.com/example/api-node-boats.git",
    )

    assert result.path == existing_repo
    assert result.cloned is False


def test_clone_support_clones_missing_required_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing repositories should be cloned into the expected root."""

    module = _load_module()
    services_root = tmp_path / "services"
    services_root.mkdir()
    calls: list[tuple[str, ...]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        calls.append(tuple(command))
        (services_root / "configd").mkdir()

    monkeypatch.setattr(module, "_run", fake_run)

    result = module.ensure_local_repository(
        name="configd",
        root_path=services_root,
        clone_url="https://github.com/example/configd.git",
    )

    assert result.path == services_root / "configd"
    assert result.cloned is True
    assert calls == [
        ("gh", "repo", "clone", "https://github.com/example/configd.git", "configd")
    ]


def test_clone_support_surfaces_failed_required_clone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failed clones should surface a focused error."""

    module = _load_module()
    services_root = tmp_path / "services"
    services_root.mkdir()

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        raise RuntimeError(f"clone failed: {' '.join(command)}")

    monkeypatch.setattr(module, "_run", fake_run)

    with pytest.raises(RuntimeError, match="clone failed"):
        module.ensure_local_repository(
            name="article-indexer",
            root_path=services_root,
            clone_url="https://github.com/example/article-indexer.git",
        )
