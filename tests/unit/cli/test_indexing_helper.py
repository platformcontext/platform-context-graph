"""Tests for CLI indexing helper idempotency behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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
        _run_index_with_progress=MagicMock(),
        watch_helper=MagicMock(),
    )
    monkeypatch.setattr(
        "platform_context_graph.cli.helpers.indexing._api",
        lambda: api,
    )

    index_helper(str(repo_path))

    query = session.run.call_args.args[0]
    assert "[:CONTAINS*]->(f:File)" in query
    assert any("already indexed with 3 files" in message for message in prints)
    graph_builder.build_graph_from_path_async.assert_not_called()
    db_manager.close_driver.assert_called_once()


def test_index_helper_raises_when_indexing_fails(
    tmp_path: Path, monkeypatch
) -> None:
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
