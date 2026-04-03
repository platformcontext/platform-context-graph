from __future__ import annotations

from pathlib import Path

import pytest

from platform_context_graph.tools.graph_builder import GraphBuilder
from platform_context_graph.tools.graph_builder_gitignore import (
    filter_repo_gitignore_files,
)
from platform_context_graph.tools.graph_builder_indexing_discovery import (
    resolve_repository_file_sets,
)


def _make_builder() -> GraphBuilder:
    builder = GraphBuilder.__new__(GraphBuilder)
    builder.parsers = {
        ".py": object(),
        ".tf": object(),
    }
    return builder


def _config_value(key: str) -> str | None:
    if key == "IGNORE_DIRS":
        return (
            "venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__"
        )
    if key == "PCG_IGNORE_DEPENDENCY_DIRS":
        return "true"
    if key == "PCG_HONOR_GITIGNORE":
        return "true"
    return None


def _config_value_gitignore_disabled(key: str) -> str | None:
    if key == "IGNORE_DIRS":
        return _config_value(key)
    if key == "PCG_IGNORE_DEPENDENCY_DIRS":
        return "true"
    if key == "PCG_HONOR_GITIGNORE":
        return "false"
    return None


def test_resolve_repository_file_sets_skips_symlink_targets_outside_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repo-scoped discovery should not crash on symlinks escaping the repo root."""

    builder = _make_builder()
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder.get_config_value", _config_value
    )

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    kept = repo / "app.py"
    kept.write_text("print('inside')\n", encoding="utf-8")

    external = tmp_path / "shared.py"
    external.write_text("print('outside')\n", encoding="utf-8")
    escaped = repo / "currency.py"
    try:
        escaped.symlink_to(external.resolve())
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable in test environment: {exc}")

    repo_file_sets = resolve_repository_file_sets(
        builder,
        repo,
        selected_repositories=[repo],
        pathspec_module=__import__("pathspec"),
    )

    assert repo_file_sets == {repo.resolve(): [kept.resolve()]}


def test_filter_repo_gitignore_files_still_skips_external_symlinks_when_disabled(
    tmp_path: Path,
) -> None:
    """Disabling .gitignore honoring must not index repo-escaping symlink targets."""

    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    kept = repo / "app.py"
    kept.write_text("print('inside')\n", encoding="utf-8")

    external = tmp_path / "shared.py"
    external.write_text("print('outside')\n", encoding="utf-8")
    escaped = repo / "currency.py"
    try:
        escaped.symlink_to(external.resolve())
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable in test environment: {exc}")

    result = filter_repo_gitignore_files(
        repo,
        [kept, escaped],
        get_config_value_fn=_config_value_gitignore_disabled,
    )

    assert result.kept_files == [kept.resolve()]
    assert result.ignored_files == []
    assert result.external_files == [escaped.absolute()]
