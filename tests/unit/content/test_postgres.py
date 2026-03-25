"""Unit tests for the PostgreSQL content provider."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.content.models import ContentEntityEntry, ContentFileEntry
from platform_context_graph.content.postgres import PostgresContentProvider
from platform_context_graph.runtime.status_store import PostgresRuntimeStatusStore


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


def test_search_file_content_false_filter_includes_legacy_plain_rows(monkeypatch) -> None:
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


def test_upsert_runtime_status_persists_ingester_status(monkeypatch) -> None:
    """Ingester status writes should upsert into the runtime status table."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_runtime_status(
        ingester="repository",
        source_mode="githubOrg",
        status="degraded",
        active_run_id="run-123",
        active_repository_path="/tmp/repos/repo-c",
        active_phase="committing",
        active_phase_started_at="2026-03-22T12:03:00+00:00",
        active_current_file="/tmp/repos/repo-c/app.js",
        active_last_progress_at="2026-03-22T12:04:00+00:00",
        active_commit_started_at="2026-03-22T12:04:30+00:00",
        last_attempt_at="2026-03-22T12:00:00+00:00",
        last_success_at="2026-03-22T11:00:00+00:00",
        next_retry_at="2026-03-22T12:05:00+00:00",
        last_error_kind="dns",
        last_error_message="temporary failure in name resolution",
        repository_count=200,
        pulled_repositories=180,
        in_sync_repositories=160,
        pending_repositories=200,
        completed_repositories=0,
        failed_repositories=0,
    )

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO runtime_ingester_status" in query
    assert params["ingester"] == "repository"
    assert params["status"] == "degraded"
    assert params["active_run_id"] == "run-123"
    assert params["active_repository_path"] == "/tmp/repos/repo-c"
    assert params["active_phase"] == "committing"
    assert params["last_error_kind"] == "dns"
    assert params["pulled_repositories"] == 180
    assert params["in_sync_repositories"] == 160
    assert params["pending_repositories"] == 200


def test_upsert_runtime_status_normalizes_null_repository_counts(monkeypatch) -> None:
    """Nullable repository count inputs should be normalized before persistence."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_runtime_status(
        ingester="repository",
        source_mode="githubOrg",
        status="degraded",
        repository_count=None,
        pulled_repositories=None,
        in_sync_repositories=None,
        pending_repositories=None,
        completed_repositories=None,
        failed_repositories=None,
    )

    _query, params = cursor.execute.call_args.args
    assert params["repository_count"] == 0
    assert params["pulled_repositories"] == 0
    assert params["in_sync_repositories"] == 0
    assert params["pending_repositories"] == 0
    assert params["completed_repositories"] == 0
    assert params["failed_repositories"] == 0


def test_get_runtime_status_returns_persisted_row(monkeypatch) -> None:
    """Ingester status reads should return the latest row for one ingester."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "ingester": "repository",
        "source_mode": "githubOrg",
        "status": "idle",
        "active_run_id": "run-123",
        "last_attempt_at": "2026-03-22T12:00:00+00:00",
        "last_success_at": "2026-03-22T12:01:00+00:00",
        "next_retry_at": None,
        "last_error_kind": None,
        "last_error_message": None,
        "repository_count": 200,
        "pulled_repositories": 200,
        "in_sync_repositories": 200,
        "pending_repositories": 0,
        "completed_repositories": 200,
        "failed_repositories": 0,
        "scan_request_state": "idle",
        "scan_request_token": None,
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
        "updated_at": "2026-03-22T12:01:00+00:00",
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.get_runtime_status(ingester="repository")

    assert result["ingester"] == "repository"
    assert result["status"] == "idle"
    assert result["completed_repositories"] == 200
    assert result["pulled_repositories"] == 200
    assert result["in_sync_repositories"] == 200
    assert result["scan_request_state"] == "idle"


def test_upsert_repository_coverage_persists_durable_repo_counts(monkeypatch) -> None:
    """Repository coverage writes should upsert durable graph/content counts."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_repository_coverage(
        run_id="run-123",
        repo_id="repository:r_ab12cd34",
        repo_name="boatgest-php-youboat",
        repo_path="/repos/boatgest-php-youboat",
        status="completed",
        phase="completed",
        finalization_status="running",
        discovered_file_count=6356,
        graph_recursive_file_count=6356,
        content_file_count=6350,
        content_entity_count=227015,
        root_file_count=2,
        root_directory_count=15,
        top_level_function_count=40271,
        class_method_count=22392,
        total_function_count=62663,
        class_count=3373,
        graph_available=True,
        server_content_available=True,
        last_error=None,
        commit_finished_at="2026-03-24T12:05:00+00:00",
        finalization_finished_at=None,
    )

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO runtime_repository_coverage" in query
    assert params["run_id"] == "run-123"
    assert params["repo_id"] == "repository:r_ab12cd34"
    assert params["graph_recursive_file_count"] == 6356
    assert params["content_file_count"] == 6350
    assert params["server_content_available"] is True


def test_get_repository_coverage_returns_latest_run_row(monkeypatch) -> None:
    """Coverage reads should return the latest matching repository coverage row."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "run_id": "run-123",
        "repo_id": "repository:r_ab12cd34",
        "repo_name": "boatgest-php-youboat",
        "repo_path": "/repos/boatgest-php-youboat",
        "status": "completed",
        "phase": "completed",
        "finalization_status": "completed",
        "discovered_file_count": 6356,
        "graph_recursive_file_count": 6356,
        "content_file_count": 6350,
        "content_entity_count": 227015,
        "root_file_count": 2,
        "root_directory_count": 15,
        "top_level_function_count": 40271,
        "class_method_count": 22392,
        "total_function_count": 62663,
        "class_count": 3373,
        "graph_available": True,
        "server_content_available": True,
        "last_error": None,
        "created_at": "2026-03-24T12:00:00+00:00",
        "updated_at": "2026-03-24T12:10:00+00:00",
        "commit_finished_at": "2026-03-24T12:05:00+00:00",
        "finalization_finished_at": "2026-03-24T12:10:00+00:00",
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.get_repository_coverage(repo_id="repository:r_ab12cd34")

    assert result is not None
    assert result["run_id"] == "run-123"
    assert result["repo_id"] == "repository:r_ab12cd34"
    assert result["graph_available"] is True
    assert result["server_content_available"] is True


def test_list_repository_coverage_supports_incomplete_filter(monkeypatch) -> None:
    """Coverage listings should support filtering to incomplete repositories."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "run_id": "run-123",
            "repo_id": "repository:r_ab12cd34",
            "repo_name": "boatgest-php-youboat",
            "repo_path": "/repos/boatgest-php-youboat",
            "status": "commit_incomplete",
            "phase": "committing",
            "finalization_status": "pending",
            "discovered_file_count": 6356,
            "graph_recursive_file_count": 6350,
            "content_file_count": 6244,
            "content_entity_count": 210000,
            "root_file_count": 2,
            "root_directory_count": 15,
            "top_level_function_count": 40271,
            "class_method_count": 22392,
            "total_function_count": 62663,
            "class_count": 3373,
            "graph_available": True,
            "server_content_available": True,
            "last_error": None,
            "created_at": "2026-03-24T12:00:00+00:00",
            "updated_at": "2026-03-24T12:10:00+00:00",
            "commit_finished_at": None,
            "finalization_finished_at": None,
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.list_repository_coverage(
        run_id="run-123",
        only_incomplete=True,
        limit=25,
    )

    query, params = cursor.execute.call_args.args
    assert "runtime_repository_coverage" in query
    assert params["run_id"] == "run-123"
    assert params["limit"] == 25
    assert result[0]["status"] == "commit_incomplete"


def test_request_scan_persists_pending_ingester_control(monkeypatch) -> None:
    """Requesting a scan should upsert a pending ingester control row."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "ingester": "repository",
        "scan_request_token": "scan-123",
        "scan_request_state": "pending",
        "scan_requested_at": "2026-03-22T12:10:00+00:00",
        "scan_requested_by": "api",
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.request_scan(ingester="repository", requested_by="api")

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO runtime_ingester_control" in query
    assert params["ingester"] == "repository"
    assert params["scan_requested_by"] == "api"
    assert result["scan_request_state"] == "pending"


def test_claim_scan_request_marks_it_running(monkeypatch) -> None:
    """Claiming a pending ingester scan should transition it to running."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "ingester": "repository",
        "scan_request_token": "scan-123",
        "scan_request_state": "running",
        "scan_requested_at": "2026-03-22T12:10:00+00:00",
        "scan_requested_by": "api",
        "scan_started_at": "2026-03-22T12:10:05+00:00",
        "scan_completed_at": None,
        "scan_error_message": None,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.claim_scan_request(ingester="repository")

    query, params = cursor.execute.call_args.args
    assert "UPDATE runtime_ingester_control" in query
    assert params["ingester"] == "repository"
    assert result["scan_request_state"] == "running"


def test_complete_scan_request_marks_it_completed(monkeypatch) -> None:
    """Completing an ingester scan request should persist the terminal state."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.complete_scan_request(ingester="repository", request_token="scan-123")

    query, params = cursor.execute.call_args.args
    assert "UPDATE runtime_ingester_control" in query
    assert params["ingester"] == "repository"
    assert params["scan_request_token"] == "scan-123"
    assert params["scan_request_state"] == "completed"
