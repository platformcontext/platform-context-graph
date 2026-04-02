"""Aggregation helpers for graph persistence metrics."""

from __future__ import annotations

from typing import Any


def accumulate_entity_totals(
    totals: dict[str, int],
    flush_metrics: dict[str, Any],
) -> None:
    """Add per-label entity row counts from one flush into a mutable aggregate."""

    for key, summary in flush_metrics.items():
        if not key.startswith("entity:"):
            continue
        label = key[len("entity:") :]
        row_count = int(summary.get("total_rows", 0))
        totals[label] = totals.get(label, 0) + row_count


__all__ = ["accumulate_entity_totals"]
