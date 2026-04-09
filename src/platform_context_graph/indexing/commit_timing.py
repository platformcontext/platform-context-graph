"""Sub-commit phase timing result for repository commit instrumentation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CommitTimingResult:
    """Accumulated timing and shape data from one repository commit.

    Populated incrementally as file batches are committed to the graph
    and content stores. Returned from the commit function and consumed
    by the pipeline to enrich per-repository telemetry.

    Attributes:
        graph_write_duration_seconds: Cumulative Neo4j graph write time.
        content_write_duration_seconds: Cumulative Postgres content write time.
        graph_batch_count: Number of graph write transaction chunks committed.
        content_batch_count: Number of content write batches committed.
        max_graph_batch_rows: Largest graph write batch by entity row count.
        max_content_batch_rows: Largest content write batch by file count.
        entity_totals: Per-label entity counts accumulated across batches.
    """

    graph_write_duration_seconds: float = 0.0
    content_write_duration_seconds: float = 0.0
    graph_batch_count: int = 0
    content_batch_count: int = 0
    max_graph_batch_rows: int = 0
    max_content_batch_rows: int = 0
    entity_totals: dict[str, int] = field(default_factory=dict)
    shared_projection_pending: bool = False
    authoritative_shared_domains: tuple[str, ...] = field(default_factory=tuple)
    accepted_generation_id: str | None = None

    def accumulate_graph_batch(
        self,
        *,
        duration_seconds: float,
        row_count: int,
    ) -> None:
        """Record one graph write batch timing and row count.

        Args:
            duration_seconds: Wall-clock time for this graph batch write.
            row_count: Number of entity rows in this batch.
        """
        self.graph_write_duration_seconds += duration_seconds
        self.graph_batch_count += 1
        if row_count > self.max_graph_batch_rows:
            self.max_graph_batch_rows = row_count

    def accumulate_content_batch(
        self,
        *,
        duration_seconds: float,
        file_count: int,
    ) -> None:
        """Record one content write batch timing and file count.

        Args:
            duration_seconds: Wall-clock time for this content batch write.
            file_count: Number of files in this batch.
        """
        self.content_write_duration_seconds += duration_seconds
        self.content_batch_count += 1
        if file_count > self.max_content_batch_rows:
            self.max_content_batch_rows = file_count

    def merge_entity_totals(self, batch_totals: dict[str, int]) -> None:
        """Merge entity counts from one batch into the cumulative totals.

        Args:
            batch_totals: Per-label entity counts from one batch.
        """
        for label, count in batch_totals.items():
            self.entity_totals[label] = self.entity_totals.get(label, 0) + count


__all__ = [
    "CommitTimingResult",
]
