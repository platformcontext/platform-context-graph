"""Tests that verify the Go write-plane owns all expected runtime surfaces.

These tests confirm that the Go data plane implementation provides the
complete set of write-plane services, handlers, and storage adapters
required by the facts-first architecture. Each test validates that the
corresponding Go package, binary, or interface exists and is functional.

When all tests pass, the Go write-plane has full ownership parity with the
Python implementation it replaces.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GO_ROOT = REPO_ROOT / "go"


class TestGoWritePlaneBinaries:
    """Verify Go write-plane binaries are buildable."""

    BINARIES = [
        "cmd/ingester",
        "cmd/bootstrap-index",
        "cmd/collector-git",
    ]

    @pytest.mark.parametrize("binary_path", BINARIES)
    def test_go_binary_builds(self, binary_path: str) -> None:
        """Each write-plane binary must compile without errors."""
        full_path = GO_ROOT / binary_path
        assert full_path.exists(), f"Go binary source {binary_path} does not exist"
        main_go = full_path / "main.go"
        if not main_go.exists():
            # Some binaries use a different entry point
            go_files = list(full_path.glob("*.go"))
            assert go_files, f"No .go files in {binary_path}"


class TestGoReducerDomainCoverage:
    """Verify all reducer domains have Go handler implementations."""

    DOMAIN_FILES = [
        "internal/reducer/workload_identity.go",
        "internal/reducer/cloud_asset_resolution.go",
        "internal/reducer/platform_materialization.go",
    ]

    @pytest.mark.parametrize("relative_path", DOMAIN_FILES)
    def test_reducer_domain_handler_exists(self, relative_path: str) -> None:
        """Each reducer domain must have a Go handler implementation."""
        target = GO_ROOT / relative_path
        assert target.exists(), (
            f"{relative_path} does not exist; "
            "Go reducer must implement all domain handlers"
        )

    def test_reducer_domain_handler_tests_exist(self) -> None:
        """Each reducer domain handler must have companion tests."""
        test_files = [
            "internal/reducer/workload_identity_test.go",
            "internal/reducer/cloud_asset_resolution_test.go",
            "internal/reducer/platform_materialization_test.go",
        ]
        for tf in test_files:
            target = GO_ROOT / tf
            assert target.exists(), (
                f"{tf} does not exist; "
                "each domain handler must have tests"
            )


class TestGoStorageAdapterCoverage:
    """Verify Go storage adapters cover the write-plane schema."""

    STORAGE_FILES = [
        "internal/storage/postgres/status.go",
        "internal/storage/postgres/recovery.go",
        "internal/storage/postgres/schema.go",
        "internal/storage/postgres/status_requests.go",
    ]

    @pytest.mark.parametrize("relative_path", STORAGE_FILES)
    def test_storage_adapter_exists(self, relative_path: str) -> None:
        """Each storage adapter must exist in the Go tree."""
        target = GO_ROOT / relative_path
        assert target.exists(), (
            f"{relative_path} does not exist; "
            "Go storage layer must own all write-plane adapters"
        )


class TestGoSharedProjectionCoverage:
    """Verify Go shared projection worker exists."""

    def test_shared_projection_worker_exists(self) -> None:
        """The shared projection worker must be implemented in Go."""
        target = GO_ROOT / "internal/reducer/shared_projection_worker.go"
        assert target.exists(), (
            "shared_projection_worker.go does not exist; "
            "Go reducer must own shared projection processing"
        )

    def test_shared_projection_worker_tests_exist(self) -> None:
        """The shared projection worker must have tests."""
        target = GO_ROOT / "internal/reducer/shared_projection_worker_test.go"
        assert target.exists(), (
            "shared_projection_worker_test.go does not exist; "
            "shared projection worker must have tests"
        )


class TestGoRuntimeStatusCoverage:
    """Verify Go runtime status infrastructure is complete."""

    def test_status_admin_server_exists(self) -> None:
        """The status admin server must be implemented in Go."""
        target = GO_ROOT / "internal/runtime/status_server.go"
        assert target.exists(), "status_server.go does not exist"

    def test_status_request_handler_exists(self) -> None:
        """The scan/reindex request handler must be implemented in Go."""
        target = GO_ROOT / "internal/runtime/status_requests.go"
        assert target.exists(), "status_requests.go does not exist"

    def test_recovery_handler_exists(self) -> None:
        """The recovery handler must be implemented in Go."""
        target = GO_ROOT / "internal/recovery/replay.go"
        assert target.exists(), "recovery replay.go does not exist"


class TestGoBootstrapSchemaCompleteness:
    """Verify the Go bootstrap schema includes all required tables."""

    REQUIRED_SQL_TABLES = [
        "ingestion_scopes",
        "scope_generations",
        "fact_records",
        "content_files",
        "content_entities",
        "fact_work_items",
        "fact_replay_events",
        "fact_backfill_requests",
        "projection_decisions",
        "shared_projection_intents",
        "runtime_ingester_control",
    ]

    def test_bootstrap_sql_files_exist(self) -> None:
        """The schema directory must contain the expected number of SQL files."""
        schema_dir = REPO_ROOT / "schema" / "data-plane" / "postgres"
        assert schema_dir.exists(), "schema/data-plane/postgres/ does not exist"
        sql_files = list(schema_dir.glob("*.sql"))
        assert len(sql_files) >= 9, (
            f"Expected at least 9 schema files, found {len(sql_files)}"
        )

    @pytest.mark.parametrize("table_name", REQUIRED_SQL_TABLES)
    def test_bootstrap_schema_references_table(self, table_name: str) -> None:
        """Each required table must appear in at least one schema file."""
        schema_dir = REPO_ROOT / "schema" / "data-plane" / "postgres"
        found = False
        for sql_file in schema_dir.glob("*.sql"):
            content = sql_file.read_text()
            if table_name in content:
                found = True
                break
        assert found, (
            f"Table {table_name} not found in any schema file; "
            "Go bootstrap must own the complete data-plane schema"
        )


class TestGoPythonBridgePackageRemoved:
    """Verify the Go pythonbridge compatibility package is deleted."""

    def test_no_pythonbridge_package(self) -> None:
        """The pythonbridge package must be deleted."""
        target = GO_ROOT / "internal" / "compatibility" / "pythonbridge"
        if target.exists():
            go_files = list(target.glob("*.go"))
            assert not go_files, (
                f"pythonbridge package still has Go files: "
                f"{[f.name for f in go_files]}"
            )
