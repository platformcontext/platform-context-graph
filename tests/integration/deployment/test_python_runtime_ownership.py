"""Tests that verify Python write-plane runtime ownership has been removed.

These tests document the complete inventory of Python runtime surfaces that
must be deleted or quarantined before the Go write-plane conversion is
complete. Each test targets one category of Python ownership.

When all tests pass, the merge bar condition "no deployed runtime or write
service starts from Python runtime entrypoints" is satisfied.

These tests are expected to FAIL until Chunk 2 (native collector/parser
cutover) completes and the final Chunk 5 deletions are applied.
"""

from __future__ import annotations

import ast
import os
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
