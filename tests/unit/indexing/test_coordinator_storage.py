"""Tests for checkpoint snapshot persistence."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.core.database import GraphStoreCapabilities
from platform_context_graph.indexing.coordinator_models import (
    RepositorySnapshot,
    RepositorySnapshotMetadata,
)
from platform_context_graph.indexing.coordinator_storage import (
    _graph_store_adapter,
    _iter_snapshot_file_data_batches,
    _load_snapshot_file_data,
    _load_snapshot_metadata,
    _save_snapshot,
)
from platform_context_graph.graph.schema.builder import (
    _schema_statements_for_capabilities,
)


def test_save_snapshot_persists_metadata_and_file_data_separately(
    tmp_path, monkeypatch
) -> None:
    """Snapshot persistence should normalize data and split heavy file payloads."""

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

    metadata = _load_snapshot_metadata("run-1234", Path(snapshot.repo_path))
    assert metadata == RepositorySnapshotMetadata(
        repo_path="/tmp/example-repo",
        file_count=1,
        imports_map={"module": ["/tmp/example-repo/src/example.py"]},
    )
    file_data = _load_snapshot_file_data("run-1234", Path(snapshot.repo_path))
    assert file_data is not None
    assert file_data[0]["metadata"]["origin"] == "/tmp/example-repo/src/example.py"


def test_iter_snapshot_file_data_batches_streams_saved_rows(
    tmp_path, monkeypatch
) -> None:
    """Saved file-data should be replayable from disk in bounded batches."""

    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator_storage.get_app_home",
        lambda: tmp_path,
    )

    snapshot = RepositorySnapshot(
        repo_path="/tmp/example-repo",
        file_count=3,
        imports_map={},
        file_data=[
            {"path": "/tmp/example-repo/src/a.py", "lang": "python"},
            {"path": "/tmp/example-repo/src/b.py", "lang": "python"},
            {"path": "/tmp/example-repo/src/c.py", "lang": "python"},
        ],
    )

    _save_snapshot("run-1234", snapshot)

    batches = list(
        _iter_snapshot_file_data_batches(
            "run-1234",
            Path(snapshot.repo_path),
            batch_size=2,
        )
    )

    assert [[item["path"] for item in batch] for batch in batches] == [
        ["/tmp/example-repo/src/a.py", "/tmp/example-repo/src/b.py"],
        ["/tmp/example-repo/src/c.py"],
    ]


def test_save_and_load_snapshot_emit_checkpoint_spans(tmp_path, monkeypatch) -> None:
    """Checkpoint persistence should surface save/load spans for tracing."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )
    span_exporter = InMemorySpanExporter()
    observability.initialize_observability(
        component="repository",
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )

    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator_storage.get_app_home",
        lambda: tmp_path,
    )

    snapshot = RepositorySnapshot(
        repo_path="/tmp/example-repo",
        file_count=1,
        imports_map={"module": ["/tmp/example-repo/src/example.py"]},
        file_data=[{"path": "/tmp/example-repo/src/example.py", "lang": "python"}],
    )

    _save_snapshot("run-1234", snapshot)
    _load_snapshot_metadata("run-1234", Path(snapshot.repo_path))
    _load_snapshot_file_data("run-1234", Path(snapshot.repo_path))

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    assert "pcg.index.checkpoint.save_snapshot_metadata" in span_names
    assert "pcg.index.checkpoint.save_snapshot_file_data" in span_names
    assert "pcg.index.checkpoint.load_snapshot_metadata" in span_names
    assert "pcg.index.checkpoint.load_snapshot_file_data" in span_names


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
        "CALL db.index.fulltext.createNodeIndex('code_search_index'" in stmt
        for stmt in neo4j_statements
    )
    assert any(
        "CALL db.idx.fulltext.createNodeIndex('Function'" in stmt
        for stmt in falkordb_statements
    )
    assert not any("FULLTEXT INDEX" in stmt for stmt in kuzu_statements)
    assert not any(
        "db.idx.fulltext.createNodeIndex" in stmt for stmt in kuzu_statements
    )
    assert any(
        "CREATE CONSTRAINT function_uid_unique" in stmt for stmt in neo4j_statements
    )
    assert any(
        "CREATE CONSTRAINT variable_uid_unique" in stmt for stmt in neo4j_statements
    )


def test_infra_fulltext_index_covers_supported_infra_labels() -> None:
    neo4j_statements = _schema_statements_for_capabilities(
        GraphStoreCapabilities(
            backend_type="neo4j",
            fulltext_index_strategy="neo4j_fulltext",
        )
    )

    infra_statement = next(
        stmt for stmt in neo4j_statements if "infra_search_index" in stmt
    )

    assert "ArgoCDApplicationSet" in infra_statement
    assert "HelmChart" in infra_statement
    assert "HelmValues" in infra_statement
    assert "KustomizeOverlay" in infra_statement
    assert "TerragruntConfig" in infra_statement
    assert "TerraformProvider" in infra_statement
    assert "TerraformLocal" in infra_statement
    assert "CloudFormationParameter" in infra_statement
    assert "CloudFormationOutput" in infra_statement
