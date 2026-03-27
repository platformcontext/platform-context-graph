"""Tests for CLI indexing helper behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from platform_context_graph.cli.helpers.indexing import index_helper


def test_index_helper_skips_when_nested_files_already_exist(
    tmp_path: Path, monkeypatch
) -> None:
    """Skip re-indexing when the repository already has descendant files."""

    repo_path = tmp_path / "repos"
    repo_path.mkdir()
    prints: list[str] = []

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.run.return_value.single.return_value = {"file_count": 3}

    driver = SimpleNamespace(session=MagicMock(return_value=session))
    db_manager = SimpleNamespace(
        get_driver=MagicMock(return_value=driver),
        close_driver=MagicMock(),
    )
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(
        list_indexed_repositories=lambda: [{"path": str(repo_path)}]
    )

    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
        _run_index_with_progress=AsyncMock(),
        watch_helper=MagicMock(),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.indexing._api",
        lambda: api,
    )

    index_helper(str(repo_path))

    query = session.run.call_args.args[0]
    assert "[:REPO_CONTAINS]->(f:File)" in query
    assert any("already indexed with 3 files" in message for message in prints)
    graph_builder.build_graph_from_path_async.assert_not_called()
    db_manager.close_driver.assert_called_once()


def test_index_helper_force_bypasses_existing_repo_skip(
    tmp_path: Path, monkeypatch
) -> None:
    """Force mode must still invoke the coordinator for already-indexed repos."""

    repo_path = tmp_path / "repos"
    repo_path.mkdir()
    prints: list[str] = []

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.run.return_value.single.return_value = {"file_count": 3}

    driver = SimpleNamespace(session=MagicMock(return_value=session))
    db_manager = SimpleNamespace(
        get_driver=MagicMock(return_value=driver),
        close_driver=MagicMock(),
    )
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(
        list_indexed_repositories=lambda: [{"path": str(repo_path)}]
    )

    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
        _run_index_with_progress=AsyncMock(),
        watch_helper=MagicMock(),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.indexing._api",
        lambda: api,
    )

    index_helper(str(repo_path), force=True)

    assert not any("already indexed with 3 files" in message for message in prints)
    api._run_index_with_progress.assert_awaited_once()
    db_manager.close_driver.assert_called_once()


def test_index_helper_raises_when_indexing_fails(tmp_path: Path, monkeypatch) -> None:
    """Bootstrap callers must see a non-zero failure when indexing crashes."""

    repo_path = tmp_path / "repos"
    repo_path.mkdir()
    prints: list[str] = []

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.run.return_value.single.return_value = {"file_count": 0}

    driver = SimpleNamespace(session=MagicMock(return_value=session))
    db_manager = SimpleNamespace(
        get_driver=MagicMock(return_value=driver),
        close_driver=MagicMock(),
    )
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(list_indexed_repositories=lambda: [])

    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
        _run_index_with_progress=MagicMock(side_effect=RuntimeError("boom")),
        watch_helper=MagicMock(),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.indexing._api",
        lambda: api,
    )

    with pytest.raises(RuntimeError, match="boom"):
        index_helper(str(repo_path))

    assert any("An error occurred during indexing:" in message for message in prints)
    db_manager.close_driver.assert_called_once()


def test_index_helper_forwards_runtime_batch_parameters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Runtime callers should be able to narrow indexing to a repo subset."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "payments-api"
    workspace.mkdir()
    repo_a.mkdir()
    prints: list[str] = []

    db_manager = SimpleNamespace(close_driver=MagicMock())
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(list_indexed_repositories=lambda: [])
    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
        _run_index_with_progress=AsyncMock(),
        watch_helper=MagicMock(),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.indexing._api",
        lambda: api,
    )

    index_helper(
        str(workspace),
        selected_repositories=[repo_a],
        family="sync",
        source="githubOrg",
        component="repository",
    )

    api._run_index_with_progress.assert_called_once_with(
        graph_builder,
        workspace.resolve(),
        is_dependency=False,
        force=False,
        selected_repositories=[repo_a.resolve()],
        family="sync",
        source="githubOrg",
        component="repository",
    )
    db_manager.close_driver.assert_called_once()


def test_index_helper_reports_effective_worker_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """CLI indexing should surface effective worker settings to the user."""

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    prints: list[str] = []

    db_manager = SimpleNamespace(close_driver=MagicMock())
    graph_builder = MagicMock()
    code_finder = SimpleNamespace(list_indexed_repositories=lambda: [])
    api = SimpleNamespace(
        console=SimpleNamespace(print=prints.append),
        _initialize_services=lambda: (db_manager, graph_builder, code_finder),
        _run_index_with_progress=AsyncMock(),
        watch_helper=MagicMock(),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.indexing._api",
        lambda: api,
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.config_manager.get_config_value",
        lambda key: {
            "PCG_PARSE_WORKERS": None,
            "PCG_INDEX_QUEUE_DEPTH": None,
            "PARALLEL_WORKERS": "6",
            "ENABLE_AUTO_WATCH": "false",
        }.get(key),
    )

    index_helper(str(workspace))

    assert any(
        "Indexing config:" in message
        and "parse workers=6" in message
        and "queue depth=12" in message
        and "legacy PARALLEL_WORKERS fallback" in message
        for message in prints
    )
