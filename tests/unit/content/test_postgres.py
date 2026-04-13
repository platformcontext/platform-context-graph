"""Unit tests for the PostgreSQL content provider."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib
from unittest.mock import MagicMock

import pytest

from platform_context_graph.content.models import ContentEntityEntry, ContentFileEntry
from platform_context_graph.content.postgres import PostgresContentProvider


def test_delete_repository_content_removes_entities_and_files(monkeypatch) -> None:
    """Deleting repository content should purge entity and file rows for one repo."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.delete_repository_content("repository:r_test")

    queries = [call.args[0] for call in cursor.execute.call_args_list]
    params = [call.args[1] for call in cursor.execute.call_args_list]
    assert queries == [
        """
                    DELETE FROM content_entities
                    WHERE repo_id = %(repo_id)s
                    """,
        """
                    DELETE FROM content_files
                    WHERE repo_id = %(repo_id)s
                    """,
    ]
    assert params == [
        {"repo_id": "repository:r_test"},
        {"repo_id": "repository:r_test"},
    ]


def test_upsert_file_persists_content_metadata(monkeypatch) -> None:
    """File upserts should write artifact metadata alongside content fields."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.upsert_file(
        ContentFileEntry(
            repo_id="repository:r_test",
            relative_path="chart/templates/_helpers.tpl",
            content='{{- define "pcg.fullname" -}}pcg{{- end -}}\n',
            language="template",
            artifact_type="helm_helper_tpl",
            template_dialect="go_template",
            iac_relevant=True,
            indexed_at=datetime.now(tz=timezone.utc),
        )
    )

    query, params = cursor.execute.call_args.args
    assert "artifact_type" in query
    assert "template_dialect" in query
    assert "iac_relevant" in query
    assert params["artifact_type"] == "helm_helper_tpl"
    assert params["template_dialect"] == "go_template"
    assert params["iac_relevant"] is True


def test_postgres_content_writes_emit_tracing_spans(monkeypatch) -> None:
    """Hot content writes should emit the expected OTEL spans."""

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
        component="api",
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.upsert_file(
        ContentFileEntry(
            repo_id="repository:r_test",
            relative_path="src/example.py",
            content="print('hello')\n",
            language="python",
            indexed_at=datetime.now(tz=timezone.utc),
        )
    )
    provider.upsert_entities(
        [
            ContentEntityEntry(
                entity_id="content-entity:e_test",
                repo_id="repository:r_test",
                relative_path="src/example.py",
                entity_type="Function",
                entity_name="hello",
                start_line=1,
                end_line=1,
                language="python",
                source_cache="def hello():\n    return 'hi'\n",
                indexed_at=datetime.now(tz=timezone.utc),
            )
        ]
    )

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    assert "pcg.content.postgres.upsert_file" in span_names
    assert "pcg.content.postgres.upsert_entities" in span_names


def test_postgres_search_spans_do_not_capture_raw_search_patterns(monkeypatch) -> None:
    """Search traces should record safe pattern metadata instead of raw user input."""

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
        component="api",
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = []

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.search_file_content(pattern="secret-token", repo_ids=["repository:r_test"])
    provider.search_entity_content(
        pattern="secret-token",
        repo_ids=["repository:r_test"],
    )

    spans_by_name = {span.name: span for span in span_exporter.get_finished_spans()}
    file_search = spans_by_name["pcg.query.content_postgres_file_search"]
    entity_search = spans_by_name["pcg.query.content_postgres_entity_search"]

    assert file_search.attributes["pcg.content.pattern_length"] == len("secret-token")
    assert file_search.attributes["pcg.content.repo_count"] == 1
    assert "pcg.content.pattern" not in file_search.attributes
    assert entity_search.attributes["pcg.content.pattern_length"] == len("secret-token")
    assert entity_search.attributes["pcg.content.repo_count"] == 1
    assert "pcg.content.pattern" not in entity_search.attributes


def test_get_file_content_returns_content_metadata(monkeypatch) -> None:
    """File reads should surface persisted metadata fields."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "repo_id": "repository:r_test",
        "relative_path": "templates/ecs/container.tpl",
        "commit_sha": "abc123",
        "content": '{"memoryReservation": ${memory}}\n',
        "content_hash": "deadbeef",
        "line_count": 1,
        "language": "template",
        "artifact_type": "terraform_template_text",
        "template_dialect": "terraform_template",
        "iac_relevant": True,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.get_file_content(
        repo_id="repository:r_test",
        relative_path="templates/ecs/container.tpl",
    )

    assert result is not None
    assert result["artifact_type"] == "terraform_template_text"
    assert result["template_dialect"] == "terraform_template"
    assert result["iac_relevant"] is True


def test_get_file_content_infers_metadata_for_legacy_rows(monkeypatch) -> None:
    """File reads should infer metadata when pre-backfill rows still contain nulls."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "repo_id": "repository:r_test",
        "relative_path": "modules/node/service/templates/default.jinja",
        "commit_sha": "abc123",
        "content": '{"name": "${name}", "cpu": ${cpu}}\n',
        "content_hash": "deadbeef",
        "line_count": 1,
        "language": "template",
        "artifact_type": None,
        "template_dialect": None,
        "iac_relevant": None,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.get_file_content(
        repo_id="repository:r_test",
        relative_path="modules/node/service/templates/default.jinja",
    )

    assert result is not None
    assert result["artifact_type"] == "terraform_template_text"
    assert result["template_dialect"] == "terraform_template"
    assert result["iac_relevant"] is True


def test_get_entity_content_returns_inherited_metadata(monkeypatch) -> None:
    """Entity reads should surface file-derived metadata."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "entity_id": "content-entity:e_test",
        "repo_id": "repository:r_test",
        "relative_path": "main.tf",
        "entity_type": "TerraformModule",
        "entity_name": "service",
        "start_line": 1,
        "end_line": 4,
        "start_byte": None,
        "end_byte": None,
        "language": "hcl",
        "source_cache": 'module "service" {\n  source = "./modules/service"\n}\n',
        "artifact_type": "terraform_hcl",
        "template_dialect": "terraform_template",
        "iac_relevant": True,
        "file_content": 'module "service" {\n  name = "${var.environment}-api"\n}\n',
        "file_artifact_type": "terraform_hcl",
        "file_template_dialect": "terraform_template",
        "file_iac_relevant": True,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.get_entity_content(entity_id="content-entity:e_test")

    assert result is not None
    assert result["artifact_type"] == "terraform_hcl"
    assert result["template_dialect"] == "terraform_template"
    assert result["iac_relevant"] is True


def test_search_file_content_falls_back_to_inferred_metadata(monkeypatch) -> None:
    """File search should not miss legacy rows whose metadata has not been backfilled."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "repo_id": "repository:r_test",
            "relative_path": "modules/node/service/templates/default.jinja",
            "language": "template",
            "artifact_type": None,
            "template_dialect": None,
            "iac_relevant": None,
            "content": '{"name": "${name}", "cpu": ${cpu}}\n',
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.search_file_content(
        pattern="${cpu}",
        artifact_types=["terraform_template_text"],
        template_dialects=["terraform_template"],
        iac_relevant=True,
    )

    query, _params = cursor.execute.call_args.args
    assert "artifact_type = ANY" not in query
    assert "template_dialect = ANY" not in query
    assert "iac_relevant =" not in query
    assert "LIMIT %(limit)s OFFSET %(offset)s" in query
    assert result["matches"][0]["artifact_type"] == "terraform_template_text"
    assert result["matches"][0]["template_dialect"] == "terraform_template"
    assert result["matches"][0]["iac_relevant"] is True


def test_search_file_content_false_filter_includes_legacy_plain_rows(
    monkeypatch,
) -> None:
    """`iac_relevant=False` searches should still match legacy rows with null metadata."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "repo_id": "repository:r_test",
            "relative_path": "README.md",
            "language": "markdown",
            "artifact_type": None,
            "template_dialect": None,
            "iac_relevant": None,
            "content": "plain project documentation\n",
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.search_file_content(
        pattern="documentation",
        iac_relevant=False,
    )

    assert result["matches"][0]["relative_path"] == "README.md"
    assert result["matches"][0]["iac_relevant"] is False


def test_search_file_content_filters_on_metadata(monkeypatch) -> None:
    """File search should support metadata filters in addition to language."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "repo_id": "repository:r_test",
            "relative_path": "Dockerfile.j2",
            "language": "dockerfile",
            "artifact_type": "dockerfile",
            "template_dialect": "jinja",
            "iac_relevant": True,
            "content": "FROM python:3.12-slim\n",
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.search_file_content(
        pattern="python:3.12-slim",
        artifact_types=["dockerfile"],
        template_dialects=["jinja"],
        iac_relevant=True,
    )

    query, params = cursor.execute.call_args.args
    assert "artifact_type = ANY" not in query
    assert "template_dialect = ANY" not in query
    assert "iac_relevant =" not in query
    assert "LIMIT %(limit)s OFFSET %(offset)s" in query
    assert params == {
        "pattern": "%python:3.12-slim%",
        "limit": 500,
        "offset": 0,
    }
    assert result["matches"][0]["artifact_type"] == "dockerfile"


def test_search_file_content_file_filter_matches_plain_source_rows(monkeypatch) -> None:
    """`artifact_types=["file"]` should match ordinary source files with null metadata."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "repo_id": "repository:r_test",
            "relative_path": "src/api_node_boats.py",
            "language": "python",
            "artifact_type": None,
            "template_dialect": None,
            "iac_relevant": None,
            "content": "from api_node_forex import warm_cache\n",
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.search_file_content(
        pattern="api_node_forex",
        artifact_types=["file"],
    )

    assert [match["relative_path"] for match in result["matches"]] == [
        "src/api_node_boats.py"
    ]
    assert result["matches"][0]["artifact_type"] is None


def test_search_entity_content_falls_back_to_inherited_metadata(monkeypatch) -> None:
    """Entity search should infer metadata for legacy rows before backfill completes."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "entity_id": "content-entity:e_test",
            "repo_id": "repository:r_test",
            "relative_path": "main.tf",
            "entity_type": "TerraformModule",
            "entity_name": "service",
            "language": "hcl",
            "artifact_type": None,
            "template_dialect": None,
            "iac_relevant": None,
            "source_cache": 'module "service" {\n  source = "./modules/service"\n}\n',
            "file_content": 'module "service" {\n  name = "${var.environment}-api"\n}\n',
            "file_artifact_type": None,
            "file_template_dialect": None,
            "file_iac_relevant": None,
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    result = provider.search_entity_content(
        pattern="service",
        artifact_types=["terraform_hcl"],
        template_dialects=["terraform_template"],
        iac_relevant=True,
    )

    query, params = cursor.execute.call_args.args
    assert "LIMIT %(limit)s OFFSET %(offset)s" in query
    assert params["limit"] == 500
    assert params["offset"] == 0
    assert result["matches"][0]["artifact_type"] == "terraform_hcl"
    assert result["matches"][0]["template_dialect"] == "terraform_template"
    assert result["matches"][0]["iac_relevant"] is True


def test_search_entity_content_qualifies_repo_filters(monkeypatch) -> None:
    """Entity search should qualify joined columns when repo filters are used."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = []

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.search_entity_content(
        pattern="CKFinder",
        repo_ids=["repository:r_test"],
        languages=["php"],
        entity_types=["Variable"],
    )

    query, params = cursor.execute.call_args.args
    assert "ce.repo_id = ANY" in query
    assert "ce.language = ANY" in query
    assert "ce.entity_type = ANY" in query
    assert params["repo_ids"] == ["repository:r_test"]
    assert params["languages"] == ["php"]
    assert params["entity_types"] == ["Variable"]


def test_upsert_entities_persists_metadata(monkeypatch) -> None:
    """Entity upserts should persist inherited metadata columns."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.upsert_entities(
        [
            ContentEntityEntry(
                entity_id="content-entity:e_test",
                repo_id="repository:r_test",
                relative_path="main.tf",
                entity_type="TerraformModule",
                entity_name="service",
                start_line=1,
                end_line=4,
                source_cache='module "service" {\n  source = "./modules/service"\n}\n',
                language="hcl",
                artifact_type="terraform_hcl",
                template_dialect="terraform_template",
                iac_relevant=True,
                indexed_at=datetime.now(tz=timezone.utc),
            )
        ]
    )

    query = cursor.executemany.call_args.args[0]
    params = cursor.executemany.call_args.args[1][0]
    assert "artifact_type" in query
    assert "template_dialect" in query
    assert "iac_relevant" in query
    assert params["artifact_type"] == "terraform_hcl"
    assert params["template_dialect"] == "terraform_template"
    assert params["iac_relevant"] is True


def test_upsert_entities_chunks_large_batches(monkeypatch) -> None:
    """Entity upserts should split large batches into smaller executemany calls."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)
    monkeypatch.setenv("PCG_CONTENT_ENTITY_UPSERT_BATCH_SIZE", "2")

    provider.upsert_entities(
        [
            ContentEntityEntry(
                entity_id=f"content-entity:e_{index}",
                repo_id="repository:r_test",
                relative_path="main.tf",
                entity_type="TerraformModule",
                entity_name=f"service_{index}",
                start_line=index + 1,
                end_line=index + 1,
                source_cache=f"module service_{index}",
                language="hcl",
            )
            for index in range(5)
        ]
    )

    assert cursor.executemany.call_count == 3
    first_chunk = cursor.executemany.call_args_list[0].args[1]
    last_chunk = cursor.executemany.call_args_list[-1].args[1]
    assert len(first_chunk) == 2
    assert len(last_chunk) == 1


def test_upsert_file_batch_chunks_large_batches(monkeypatch) -> None:
    """Batch file upserts should split large batches into smaller executemany calls."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)
    monkeypatch.setenv("PCG_CONTENT_FILE_UPSERT_BATCH_SIZE", "2")

    entries = [
        ContentFileEntry(
            repo_id="repository:r_test",
            relative_path=f"src/file_{i}.py",
            content=f"print({i})\n",
            language="python",
            indexed_at=datetime.now(tz=timezone.utc),
        )
        for i in range(3)
    ]
    provider.upsert_file_batch(entries)

    assert cursor.executemany.call_count == 2
    first_chunk = cursor.executemany.call_args_list[0].args[1]
    last_chunk = cursor.executemany.call_args_list[-1].args[1]
    assert len(first_chunk) == 2
    assert len(last_chunk) == 1
    assert first_chunk[0]["relative_path"] == "src/file_0.py"
    assert last_chunk[0]["relative_path"] == "src/file_2.py"


def test_upsert_file_batch_skips_empty_list(monkeypatch) -> None:
    """Batch file upserts should be a no-op when the entry list is empty."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.upsert_file_batch([])

    assert cursor.executemany.call_count == 0


def test_upsert_entities_batch_uses_executemany(monkeypatch) -> None:
    """Batch entity upserts should persist all rows via executemany."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    entries = [
        ContentEntityEntry(
            entity_id=f"content-entity:e_batch_{i}",
            repo_id="repository:r_test",
            relative_path=f"src/file_{i}.py",
            entity_type="Function",
            entity_name=f"func_{i}",
            start_line=1,
            end_line=5,
            source_cache=f"def func_{i}(): pass\n",
            language="python",
            indexed_at=datetime.now(tz=timezone.utc),
        )
        for i in range(4)
    ]
    provider.upsert_entities_batch(entries)

    assert cursor.executemany.call_count == 1
    rows = cursor.executemany.call_args.args[1]
    assert len(rows) == 4


def test_upsert_entities_batch_chunks_large_batches(monkeypatch) -> None:
    """Batch entity upserts should split at the configured batch size."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)
    monkeypatch.setenv("PCG_CONTENT_ENTITY_UPSERT_BATCH_SIZE", "3")

    entries = [
        ContentEntityEntry(
            entity_id=f"content-entity:e_chunk_{i}",
            repo_id="repository:r_test",
            relative_path="app.py",
            entity_type="Function",
            entity_name=f"fn_{i}",
            start_line=i + 1,
            end_line=i + 1,
            source_cache=f"def fn_{i}(): ...\n",
            language="python",
        )
        for i in range(7)
    ]
    provider.upsert_entities_batch(entries)

    assert cursor.executemany.call_count == 3
    assert len(cursor.executemany.call_args_list[0].args[1]) == 3
    assert len(cursor.executemany.call_args_list[2].args[1]) == 1


def test_upsert_entities_batch_skips_empty_list(monkeypatch) -> None:
    """Batch entity upserts should be a no-op when the entry list is empty."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.upsert_entities_batch([])

    assert cursor.executemany.call_count == 0


def test_provider_uses_pool_when_available(monkeypatch) -> None:
    """Provider should create a connection pool when psycopg_pool is available."""

    import platform_context_graph.content.postgres as pg_mod

    mock_pool_instance = MagicMock()
    mock_pool_class = MagicMock(return_value=mock_pool_instance)
    original_pool = pg_mod._ConnectionPool
    monkeypatch.setattr(pg_mod, "_ConnectionPool", mock_pool_class)

    try:
        provider = PostgresContentProvider("postgresql://example")
        assert provider._pool is mock_pool_instance
        assert provider._conn_lock is None
        mock_pool_class.assert_called_once()
    finally:
        monkeypatch.setattr(pg_mod, "_ConnectionPool", original_pool)


def test_provider_falls_back_without_pool(monkeypatch) -> None:
    """Provider should use a single connection when psycopg_pool is missing."""

    import platform_context_graph.content.postgres as pg_mod

    monkeypatch.setattr(pg_mod, "_ConnectionPool", None)

    provider = PostgresContentProvider("postgresql://example")

    assert provider._pool is None
    assert provider._conn_lock is not None


def test_provider_falls_back_on_pool_init_failure(monkeypatch) -> None:
    """Provider should fall back to single-conn when pool creation raises."""

    import platform_context_graph.content.postgres as pg_mod

    def _raise(*args, **kwargs):
        raise RuntimeError("pool init failed")

    monkeypatch.setattr(pg_mod, "_ConnectionPool", _raise)

    provider = PostgresContentProvider("postgresql://example")

    assert provider._pool is None
    assert provider._conn_lock is not None


def test_close_with_pool(monkeypatch) -> None:
    """Closing the provider should close the pool when in pool mode."""

    import platform_context_graph.content.postgres as pg_mod

    mock_pool = MagicMock()
    mock_pool_class = MagicMock(return_value=mock_pool)
    monkeypatch.setattr(pg_mod, "_ConnectionPool", mock_pool_class)

    provider = PostgresContentProvider("postgresql://example")
    provider.close()

    mock_pool.close.assert_called_once()
    assert provider._pool is None


def test_cursor_uses_pool_connection(monkeypatch) -> None:
    """The cursor context manager should get a connection from the pool."""

    import platform_context_graph.content.postgres as pg_mod

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool_class = MagicMock(return_value=mock_pool)
    monkeypatch.setattr(pg_mod, "_ConnectionPool", mock_pool_class)

    provider = PostgresContentProvider("postgresql://example")
    provider._initialized = True  # skip schema init

    with provider._cursor() as cursor:
        assert cursor is mock_cursor

