"""Tests for checkpoint snapshot persistence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.core.database import GraphStoreCapabilities
from platform_context_graph.indexing.coordinator_models import RepositorySnapshot
from platform_context_graph.indexing.coordinator_storage import (
    _graph_store_adapter,
    _load_snapshot,
    _save_snapshot,
)
from platform_context_graph.tools.graph_builder_schema import (
    _schema_statements_for_capabilities,
)


def test_save_snapshot_serializes_nested_path_values(tmp_path, monkeypatch) -> None:
    """Snapshot persistence should normalize nested ``Path`` values to strings."""

    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator_storage.get_app_home",
        lambda: tmp_path,
    )

    snapshot = RepositorySnapshot(
        repo_path="/tmp/example-repo",
        file_count=1,
        imports_map={"module": ["/tmp/example-repo/src/example.py"]},
        file_data=[
            {
                "path": "/tmp/example-repo/src/example.py",
                "lang": "python",
                "metadata": {
                    "origin": Path("/tmp/example-repo/src/example.py"),
                },
            }
        ],
    )

    _save_snapshot("run-1234", snapshot)

    loaded = _load_snapshot("run-1234", Path(snapshot.repo_path))
    assert loaded is not None
    assert (
        loaded.file_data[0]["metadata"]["origin"] == "/tmp/example-repo/src/example.py"
    )


def test_graph_store_adapter_exposes_capabilities_and_builder_entrypoints() -> None:
    """Coordinator storage should interact with graph backends via one adapter."""

    create_schema = MagicMock()
    delete_repository = MagicMock(return_value=True)
    builder = SimpleNamespace(
        db_manager=SimpleNamespace(
            graph_store_capabilities=lambda: GraphStoreCapabilities(
                backend_type="falkordb",
                fulltext_index_strategy="falkordb_procedure",
            )
        ),
        create_schema=create_schema,
        delete_repository_from_graph=delete_repository,
    )

    adapter = _graph_store_adapter(builder)

    assert adapter.capabilities == GraphStoreCapabilities(
        backend_type="falkordb",
        fulltext_index_strategy="falkordb_procedure",
    )
    adapter.initialize_schema()
    adapter.delete_repository("/tmp/workspace/repo")
    create_schema.assert_called_once_with()
    delete_repository.assert_called_once_with("/tmp/workspace/repo")


def test_graph_store_adapter_falls_back_to_backend_type_capabilities() -> None:
    """Older managers without explicit capabilities should still resolve defaults."""

    builder = SimpleNamespace(
        db_manager=SimpleNamespace(get_backend_type=lambda: "neo4j"),
        create_schema=lambda: None,
        delete_repository_from_graph=lambda _repo_path: True,
    )

    adapter = _graph_store_adapter(builder)

    assert adapter.capabilities == GraphStoreCapabilities(
        backend_type="neo4j",
        fulltext_index_strategy="neo4j_fulltext",
    )


def test_schema_statements_follow_graph_store_capabilities() -> None:
    """Schema initialization should derive fulltext behavior from capabilities."""

    neo4j_statements = _schema_statements_for_capabilities(
        GraphStoreCapabilities(
            backend_type="neo4j",
            fulltext_index_strategy="neo4j_fulltext",
        )
    )
    falkordb_statements = _schema_statements_for_capabilities(
        GraphStoreCapabilities(
            backend_type="falkordb",
            fulltext_index_strategy="falkordb_procedure",
        )
    )
    kuzu_statements = _schema_statements_for_capabilities(
        GraphStoreCapabilities(
            backend_type="kuzudb",
            fulltext_index_strategy="none",
        )
    )

    assert any(
        "CREATE FULLTEXT INDEX code_search_index" in stmt for stmt in neo4j_statements
    )
    assert any(
        "CALL db.idx.fulltext.createNodeIndex('Function'" in stmt
        for stmt in falkordb_statements
    )
    assert not any("FULLTEXT INDEX" in stmt for stmt in kuzu_statements)
    assert not any(
        "db.idx.fulltext.createNodeIndex" in stmt for stmt in kuzu_statements
    )
