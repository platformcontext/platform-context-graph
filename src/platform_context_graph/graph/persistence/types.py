"""Shared result types for graph persistence workflows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BatchCommitResult:
    """Describe files committed successfully with timing and entity counts."""

    committed_file_paths: tuple[str, ...] = ()
    failed_file_paths: tuple[str, ...] = ()
    content_write_duration_seconds: float = 0.0
    graph_write_duration_seconds: float = 0.0
    entity_totals: dict[str, int] = field(default_factory=dict)

    @property
    def committed_file_count(self) -> int:
        """Return the number of files that reached durable graph state."""
        return len(self.committed_file_paths)

    @property
    def last_committed_file(self) -> str | None:
        """Return the final committed file path when any succeeded."""
        if not self.committed_file_paths:
            return None
        return self.committed_file_paths[-1]
