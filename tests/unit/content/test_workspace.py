"""Unit tests for workspace-backed content retrieval."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from platform_context_graph.content.workspace import (
    WorkspaceContentProvider,
    _resolve_repository,
)


def _provider_for_repo(local_path: Path) -> WorkspaceContentProvider:
    """Create a workspace provider with repository resolution stubbed out."""

    provider = WorkspaceContentProvider(database=MagicMock())
    provider._resolve_repository = MagicMock(  # type: ignore[method-assign]
        return_value={
            "id": "repository:r_ab12cd34",
            "name": "payments-api",
            "local_path": str(local_path),
            "remote_url": "https://github.com/platformcontext/payments-api",
            "repo_slug": "platformcontext/payments-api",
            "has_remote": True,
        }
    )
    return provider


class _RowWrapper:
    """Row wrapper that exposes `.data()` but breaks plain `dict(row)` casting."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def data(self) -> dict[str, object]:
        return dict(self._payload)

    def __iter__(self):
        return iter(self._payload)


class _Session:
    """Minimal session stub for repository resolution tests."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def run(self, _query: str, **_kwargs):
        class _Result:
            def __init__(self, rows: list[object]) -> None:
                self._rows = rows

            def data(self) -> list[object]:
                return list(self._rows)

        return _Result(self._rows)


def test_get_file_content_rejects_paths_outside_repository(temp_test_dir: Path) -> None:
    """Do not allow repo-relative lookups to escape the repository root."""

    repo_root = temp_test_dir / "repo"
    repo_root.mkdir()
    outside_file = temp_test_dir / "secret.txt"
    outside_file.write_text("top secret\n", encoding="utf-8")
    provider = _provider_for_repo(repo_root)

    result = provider.get_file_content(
        repo_id="repository:r_ab12cd34",
        relative_path="../secret.txt",
    )

    assert result == {
        "available": False,
        "repo_id": "repository:r_ab12cd34",
        "relative_path": "../secret.txt",
        "content": None,
        "source_backend": "unavailable",
    }


def test_get_file_lines_rejects_paths_outside_repository(temp_test_dir: Path) -> None:
    """Do not leak line content for repo-relative paths outside the repo root."""

    repo_root = temp_test_dir / "repo"
    repo_root.mkdir()
    outside_file = temp_test_dir / "secret.txt"
    outside_file.write_text("top secret\n", encoding="utf-8")
    provider = _provider_for_repo(repo_root)

    result = provider.get_file_lines(
        repo_id="repository:r_ab12cd34",
        relative_path="../secret.txt",
        start_line=1,
        end_line=1,
    )

    assert result == {
        "available": False,
        "repo_id": "repository:r_ab12cd34",
        "relative_path": "../secret.txt",
        "start_line": 1,
        "end_line": 1,
        "lines": [],
        "source_backend": "unavailable",
        "repo_access": None,
    }


def test_get_file_content_blocks_dependency_paths_by_default(
    temp_test_dir: Path, monkeypatch
) -> None:
    """Workspace fallback should not expose files inside built-in dependency roots."""

    monkeypatch.delenv("PCG_IGNORE_DEPENDENCY_DIRS", raising=False)
    repo_root = temp_test_dir / "repo"
    vendored_file = repo_root / "js" / "plugins" / "vendor" / "autoload.php"
    vendored_file.parent.mkdir(parents=True)
    vendored_file.write_text("<?php\n", encoding="utf-8")
    provider = _provider_for_repo(repo_root)

    result = provider.get_file_content(
        repo_id="repository:r_ab12cd34",
        relative_path="js/plugins/vendor/autoload.php",
    )

    assert result == {
        "available": False,
        "repo_id": "repository:r_ab12cd34",
        "relative_path": "js/plugins/vendor/autoload.php",
        "content": None,
        "source_backend": "unavailable",
    }


def test_get_file_content_allows_dependency_paths_when_disabled(
    temp_test_dir: Path, monkeypatch
) -> None:
    """Workspace fallback should honor the explicit dependency-ignore override."""

    monkeypatch.setenv("PCG_IGNORE_DEPENDENCY_DIRS", "false")
    repo_root = temp_test_dir / "repo"
    vendored_file = repo_root / "js" / "plugins" / "vendor" / "autoload.php"
    vendored_file.parent.mkdir(parents=True)
    vendored_file.write_text("<?php\n", encoding="utf-8")
    provider = _provider_for_repo(repo_root)

    result = provider.get_file_content(
        repo_id="repository:r_ab12cd34",
        relative_path="js/plugins/vendor/autoload.php",
    )

    assert result["available"] is True
    assert result["relative_path"] == "js/plugins/vendor/autoload.php"
    assert result["content"] == "<?php\n"
    assert result["source_backend"] == "workspace"


def test_resolve_repository_accepts_materialized_row_wrappers() -> None:
    """Repository resolution should accept `.data()` row wrappers directly."""

    session = _Session(
        [
            _RowWrapper(
                {
                    "id": "repository:r_ab12cd34",
                    "name": "payments-api",
                    "path": "/repos/payments-api",
                    "local_path": "/repos/payments-api",
                    "remote_url": "https://github.com/platformcontext/payments-api",
                    "repo_slug": "platformcontext/payments-api",
                    "has_remote": True,
                }
            )
        ]
    )

    result = _resolve_repository(session, "payments-api")

    assert result is not None
    assert result["id"] == "repository:r_ab12cd34"
    assert result["repo_slug"] == "platformcontext/payments-api"
