"""Batch flush orchestration for cross-file graph writes."""

from __future__ import annotations

import time
from typing import Any

from ...observability import get_observability
from ...utils.debug_log import debug_logger, emit_log_call
from .batch_support import (
    _DEFAULT_ENTITY_BATCH_SIZE,
    _ENTITY_BATCH_SIZE_BY_LABEL,
    _WRITE_BATCH_FLUSH_ROW_THRESHOLD,
    collect_file_write_data,
    empty_accumulator,
    has_pending_rows,
    log_prepared_entity_batches,
    merge_batches,
    pending_row_count,
    should_flush_batches,
    summarize_entity_source_files,
)
from .unwind import (
    run_class_function_unwind,
    run_entity_unwind,
    run_generic_import_unwind,
    run_js_import_unwind,
    run_module_inclusion_unwind,
    run_module_unwind,
    run_nested_function_unwind,
    run_parameter_unwind,
)


def flush_write_batches(
    tx: Any,
    batches: dict[str, Any],
    *,
    info_logger_fn: Any | None = None,
    debug_logger_fn: Any | None = None,
    entity_batch_size: int | None = None,
) -> dict[str, dict[str, float | int]]:
    """Flush all accumulated write batches through UNWIND queries."""
    batch_metrics: dict[str, dict[str, float | int]] = {}
    telemetry = get_observability()
    for label, rows in batches["entities_by_label"].items():
        summary = _flush_entity_label_batches(
            tx,
            label,
            rows,
            info_logger_fn=info_logger_fn,
            entity_batch_size=entity_batch_size,
        )
        batch_metrics[f"entity:{label}"] = summary
        telemetry.record_graph_write_batch(
            batch_type="entity",
            label=label,
            rows=int(summary["total_rows"]),
            duration_seconds=float(summary["duration_seconds"]),
        )
        if callable(debug_logger_fn):
            emit_log_call(
                debug_logger_fn,
                f"Graph write batch entity label={label} "
                f"rows={summary['total_rows']} "
                f"uid_rows={summary['uid_rows']} "
                f"name_rows={summary['name_rows']} "
                f"chunks={summary['chunk_count']} "
                f"max_chunk_rows={summary['max_chunk_rows']} "
                f"duration={summary['duration_seconds']:.2f}s",
                event_name="graph.batch.entity.flush",
                extra_keys={
                    "label": label,
                    "rows": summary["total_rows"],
                    "uid_rows": summary["uid_rows"],
                    "name_rows": summary["name_rows"],
                    "chunk_count": summary["chunk_count"],
                    "max_chunk_rows": summary["max_chunk_rows"],
                    "duration_seconds": round(float(summary["duration_seconds"]), 6),
                },
            )

    for batch_name, rows, runner in (
        ("parameters", batches["params_rows"], run_parameter_unwind),
        ("modules", batches["module_rows"], run_module_unwind),
        ("nested_functions", batches["nested_fn_rows"], run_nested_function_unwind),
        ("class_functions", batches["class_fn_rows"], run_class_function_unwind),
        (
            "module_inclusions",
            batches["module_inclusion_rows"],
            run_module_inclusion_unwind,
        ),
        ("js_imports", batches["js_import_rows"], run_js_import_unwind),
        (
            "generic_imports",
            batches["generic_import_rows"],
            run_generic_import_unwind,
        ),
    ):
        if not rows:
            continue
        started = time.perf_counter()
        runner(tx, rows)
        elapsed = time.perf_counter() - started
        batch_metrics[batch_name] = {
            "rows": len(rows),
            "duration_seconds": elapsed,
        }
        telemetry.record_graph_write_batch(
            batch_type=batch_name,
            label=None,
            rows=len(rows),
            duration_seconds=elapsed,
        )
        if callable(debug_logger_fn):
            emit_log_call(
                debug_logger_fn,
                f"Graph write batch type={batch_name} rows={len(rows)} duration={elapsed:.2f}s",
                event_name="graph.batch.flush",
                extra_keys={
                    "batch_type": batch_name,
                    "rows": len(rows),
                    "duration_seconds": round(elapsed, 6),
                },
            )
    return batch_metrics


def _flush_entity_label_batches(
    tx: Any,
    label: str,
    rows: list[dict[str, Any]],
    *,
    info_logger_fn: Any | None = None,
    entity_batch_size: int | None = None,
) -> dict[str, float | int]:
    """Flush one entity label, chunking only where the label needs it."""
    if not rows:
        return {
            "total_rows": 0,
            "uid_rows": 0,
            "name_rows": 0,
            "duration_seconds": 0.0,
            "chunk_count": 0,
            "max_chunk_rows": 0,
        }

    label_specific = _ENTITY_BATCH_SIZE_BY_LABEL.get(label)
    if label_specific is not None:
        chunk_size = label_specific
    elif entity_batch_size is not None:
        chunk_size = entity_batch_size
    else:
        chunk_size = _DEFAULT_ENTITY_BATCH_SIZE
    total_rows = 0
    uid_rows = 0
    name_rows = 0
    duration_seconds = 0.0
    chunk_count = 0
    max_chunk_rows = 0

    total_chunks = max(1, (len(rows) + chunk_size - 1) // chunk_size)
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        chunk_number = chunk_count + 1
        emit_log_call(
            debug_logger,
            f"Graph write batch entity start "
            f"label={label} chunk={chunk_number}/{total_chunks} rows={len(chunk)}",
            event_name="graph.batch.chunk.started",
            extra_keys={
                "label": label,
                "chunk_number": chunk_number,
                "total_chunks": total_chunks,
                "rows": len(chunk),
            },
        )
        chunk_summary = run_entity_unwind(tx, label, chunk)
        total_rows += int(chunk_summary["total_rows"])
        uid_rows += int(chunk_summary["uid_rows"])
        name_rows += int(chunk_summary["name_rows"])
        duration_seconds += float(chunk_summary["duration_seconds"])
        chunk_count += 1
        max_chunk_rows = max(max_chunk_rows, len(chunk))
        emit_log_call(
            debug_logger,
            f"Graph write batch entity done "
            f"label={label} chunk={chunk_number}/{total_chunks} "
            f"rows={len(chunk)} duration={float(chunk_summary['duration_seconds']):.2f}s",
            event_name="graph.batch.chunk.completed",
            extra_keys={
                "label": label,
                "chunk_number": chunk_number,
                "total_chunks": total_chunks,
                "rows": len(chunk),
                "duration_seconds": round(float(chunk_summary["duration_seconds"]), 6),
            },
        )

    return {
        "total_rows": total_rows,
        "uid_rows": uid_rows,
        "name_rows": name_rows,
        "duration_seconds": duration_seconds,
        "chunk_count": chunk_count,
        "max_chunk_rows": max_chunk_rows,
    }


__all__ = [
    "_WRITE_BATCH_FLUSH_ROW_THRESHOLD",
    "collect_file_write_data",
    "empty_accumulator",
    "flush_write_batches",
    "has_pending_rows",
    "log_prepared_entity_batches",
    "merge_batches",
    "pending_row_count",
    "should_flush_batches",
    "summarize_entity_source_files",
]
