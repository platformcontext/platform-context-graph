"""Fact emission helpers for source-specific collectors."""

from .git_snapshot import GitSnapshotFactEmissionResult
from .git_snapshot import emit_git_snapshot_facts

__all__ = [
    "GitSnapshotFactEmissionResult",
    "emit_git_snapshot_facts",
]
