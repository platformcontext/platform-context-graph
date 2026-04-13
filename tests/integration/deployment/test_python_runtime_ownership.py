"""Tests that verify Python write-plane runtime ownership has been removed.

These tests document the complete inventory of Python runtime surfaces that
must be deleted or quarantined before the Go write-plane conversion is
complete. Each test targets one category of Python ownership.

When all tests pass, the merge bar condition "no deployed runtime or write
service starts from Python runtime entrypoints" is satisfied and the remaining
Python resolution, facts, and status-store ownership surfaces have been
removed.

These tests are expected to FAIL until Chunk 2 (native collector/parser
cutover) completes and the final Chunk 5 deletions are applied.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src" / "platform_context_graph"


class TestPythonRuntimeCommandsRemoved:
    """Verify Python CLI runtime commands no longer own write-plane services."""

    def test_no_python_bootstrap_index_command(self) -> None:
        """The Python 'bootstrap-index' internal command must not exist."""
        runtime_py = SRC_ROOT / "cli" / "commands" / "runtime.py"
        if not runtime_py.exists():
            return  # File already deleted — pass
        content = runtime_py.read_text()
        assert "bootstrap-index" not in content, (
            "Python CLI still registers 'bootstrap-index' command; "
            "Go owns this via /usr/local/bin/pcg-bootstrap-index"
        )

    def test_no_python_repo_sync_loop_command(self) -> None:
        """The Python 'repo-sync-loop' internal command must not exist."""
        runtime_py = SRC_ROOT / "cli" / "commands" / "runtime.py"
        if not runtime_py.exists():
            return
        content = runtime_py.read_text()
        assert "repo-sync-loop" not in content, (
            "Python CLI still registers 'repo-sync-loop' command; "
            "Go owns this via /usr/local/bin/pcg-ingester"
        )

    def test_no_python_resolution_engine_command(self) -> None:
        """The Python 'resolution-engine' internal command must not exist."""
        runtime_py = SRC_ROOT / "cli" / "commands" / "runtime.py"
        if not runtime_py.exists():
            return
        content = runtime_py.read_text()
        assert "resolution-engine" not in content, (
            "Python CLI still registers 'resolution-engine' command; "
            "Go owns this via /usr/local/bin/pcg-reducer"
        )


class TestPythonFinalizationBridgeRemoved:
    """Verify Python finalization/recovery bridge modules are deleted."""

    def test_no_post_commit_writer(self) -> None:
        """The legacy post_commit_writer must be deleted."""
        target = SRC_ROOT / "indexing" / "post_commit_writer.py"
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go recovery package replaces this"
        )

    def test_no_collector_finalize(self) -> None:
        """The collector finalize module must be deleted."""
        target = SRC_ROOT / "collectors" / "git" / "finalize.py"
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go projector/reducer pipeline replaces finalization"
        )

    def test_no_coordinator_finalize(self) -> None:
        """The coordinator finalize module must be deleted."""
        target = SRC_ROOT / "indexing" / "coordinator_finalize.py"
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go projector/reducer pipeline replaces finalization"
        )

    def test_no_cli_finalize_helper(self) -> None:
        """The CLI finalize helper must be deleted."""
        target = SRC_ROOT / "cli" / "helpers" / "finalize.py"
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go recovery handler replaces CLI finalize"
        )


class TestPythonResolutionOwnershipRemoved:
    """Verify Python resolution ownership is removed from the write plane."""

    RESOLUTION_FILES = [
        "resolution/platforms.py",
        "resolution/platform_families.py",
        "resolution/decisions/postgres.py",
        "resolution/orchestration/runtime.py",
        "resolution/orchestration/engine.py",
        "resolution/orchestration/failure_classification.py",
        "resolution/shared_projection/runtime.py",
        "resolution/shared_projection/emission.py",
        "resolution/shared_projection/partitioning.py",
        "resolution/shared_projection/postgres.py",
        "resolution/shared_projection/platform_domain.py",
        "resolution/shared_projection/dependency_domain.py",
        "resolution/shared_projection/dependency_runtime_support.py",
        "resolution/shared_projection/followup.py",
        "resolution/shared_projection/models.py",
        "resolution/shared_projection/schema.py",
        "resolution/projection/entities.py",
        "resolution/projection/files.py",
        "resolution/projection/relationships.py",
        "resolution/projection/workloads.py",
        "resolution/projection/repositories.py",
        "resolution/projection/common.py",
        "resolution/maintenance/platform_cleanup.py",
    ]

    @pytest.mark.parametrize("relative_path", RESOLUTION_FILES)
    def test_no_python_resolution_module(self, relative_path: str) -> None:
        """Each Python resolution ownership module must be deleted."""
        target = SRC_ROOT / relative_path
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go projector/reducer implementations own resolution logic"
        )


class TestPythonFactsOwnershipRemoved:
    """Verify Python facts ownership is removed from the write plane."""

    FACTS_FILES = [
        "facts/state.py",
        "facts/emission/git_snapshot.py",
        "facts/storage/postgres.py",
        "facts/storage/queries.py",
        "facts/storage/schema.py",
        "facts/storage/sql.py",
        "facts/work_queue/postgres.py",
        "facts/work_queue/recovery.py",
        "facts/work_queue/replay.py",
        "facts/work_queue/claims.py",
        "facts/work_queue/models.py",
        "facts/work_queue/schema.py",
        "facts/work_queue/stages.py",
        "facts/work_queue/failure_types.py",
        "facts/work_queue/inspection.py",
        "facts/work_queue/support.py",
        "facts/work_queue/shared_completion.py",
    ]

    @pytest.mark.parametrize("relative_path", FACTS_FILES)
    def test_no_python_facts_module(self, relative_path: str) -> None:
        """Each Python facts ownership module must be deleted."""
        target = SRC_ROOT / relative_path
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go facts storage and queue ownership replaces Python facts logic"
        )


class TestPythonStatusStoreOwnershipRemoved:
    """Verify Python runtime status-store ownership is removed."""

    STATUS_STORE_FILES = [
        "runtime/status_store.py",
        "runtime/status_store_db.py",
        "runtime/status_store_runtime.py",
        "runtime/status_store_support.py",
    ]

    @pytest.mark.parametrize("relative_path", STATUS_STORE_FILES)
    def test_no_python_status_store_module(self, relative_path: str) -> None:
        """Each Python status-store ownership module must be deleted."""
        target = SRC_ROOT / relative_path
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go status-store parity owns scan/reindex and coverage lifecycle"
        )


class TestPythonCollectorBridgeRemoved:
    """Verify Python Go-collector bridge modules are deleted.

    These tests are blocked on Chunk 2 (native collector/parser cutover).
    """

    BRIDGE_FILES = [
        "go_collector_bridge.py",
        "go_collector_bridge_facts.py",
        "go_collector_selection_bridge.py",
        "go_collector_snapshot_bridge.py",
        "go_collector_snapshot_collection.py",
    ]

    @pytest.mark.parametrize("filename", BRIDGE_FILES)
    def test_no_python_bridge_module(self, filename: str) -> None:
        """Each Go-collector Python bridge module must be deleted."""
        target = SRC_ROOT / "runtime" / "ingester" / filename
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "blocked on Chunk 2 native collector cutover"
        )


class TestGoPythonBridgeImportsRemoved:
    """Verify no Go runtime service imports the pythonbridge package."""

    def test_no_pythonbridge_imports_in_go_cmd(self) -> None:
        """No Go cmd/ binary should import compatibility/pythonbridge."""
        go_cmd = REPO_ROOT / "go" / "cmd"
        if not go_cmd.exists():
            return

        violations = []
        for go_file in go_cmd.rglob("*.go"):
            content = go_file.read_text()
            if "compatibility/pythonbridge" in content:
                violations.append(str(go_file.relative_to(REPO_ROOT)))

        assert not violations, (
            "Go cmd/ binaries still import pythonbridge:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\nBlocked on Chunk 2 native collector cutover"
        )


class TestPythonParserRuntimeOwnershipRemoved:
    """Verify runtime modules no longer import parser-owned Python helpers."""

    def test_no_src_runtime_module_imports_parser_package(self) -> None:
        """Modules outside `parsers/` should not import parser packages."""

        violations: list[str] = []
        for target in SRC_ROOT.rglob("*.py"):
            relative_path = target.relative_to(SRC_ROOT)
            if relative_path.parts[0] == "parsers":
                continue

            tree = ast.parse(target.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(
                        alias.name.startswith("platform_context_graph.parsers")
                        for alias in node.names
                    ):
                        violations.append(str(relative_path))
                        break
                if isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    if "parsers" in module_name:
                        violations.append(str(relative_path))
                        break

        assert not violations, (
            "Runtime modules outside src/platform_context_graph/parsers still "
            "import the Python parser package:\n"
            + "\n".join(f"  - {path}" for path in sorted(set(violations)))
        )

    def test_no_python_parser_registry_module(self) -> None:
        """The legacy Python parser registry should be deleted."""

        target = SRC_ROOT / "parsers" / "registry.py"
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go parser registry ownership replaces this Python scaffold"
        )

    def test_no_python_parser_raw_text_module(self) -> None:
        """The legacy Python raw-text parser registry helper should be deleted."""

        target = SRC_ROOT / "parsers" / "raw_text.py"
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go parser registry ownership replaces this Python scaffold"
        )

    @pytest.mark.parametrize(
        "relative_path",
        [
            "parsers/languages/dockerfile.py",
            "parsers/languages/dockerfile_support.py",
            "parsers/languages/groovy.py",
            "parsers/languages/rust.py",
        ],
    )
    def test_deleted_python_parser_facades_stay_gone(self, relative_path: str) -> None:
        """Go-owned parser families should not keep Python facade modules."""

        target = SRC_ROOT / relative_path
        assert not target.exists(), (
            f"{target.relative_to(REPO_ROOT)} still exists; "
            "Go parser ownership has replaced this Python parser facade"
        )
