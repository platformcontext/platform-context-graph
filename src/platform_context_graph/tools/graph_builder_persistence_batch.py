"""Batch data collection and lifecycle helpers for cross-file Neo4j writes."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import time
from typing import Any

from ..content.ingest import CONTENT_ENTITY_LABELS
from ..observability import get_observability
from ..utils.debug_log import debug_logger
from .graph_builder_persistence_unwind import (
    ITEM_MAPPINGS_KEYS,
    entity_props_for_unwind,
    run_class_function_unwind,
    run_entity_unwind,
    run_generic_import_unwind,
    run_js_import_unwind,
    run_module_inclusion_unwind,
    run_module_unwind,
    run_nested_function_unwind,
    run_parameter_unwind,
)

_DEFAULT_ENTITY_BATCH_SIZE = 10_000
_ENTITY_BATCH_SIZE_BY_LABEL = {
    "Variable": 100,
}
_LARGE_LABEL_SUMMARY_THRESHOLD = 1_000
_WRITE_BATCH_FLUSH_ROW_THRESHOLD = 2_000
_NON_ENTITY_BATCH_KEYS = (
    "params_rows",
    "module_rows",
    "nested_fn_rows",
    "class_fn_rows",
    "module_inclusion_rows",
    "js_import_rows",
    "generic_import_rows",
)


def collect_file_write_data(
    file_data: dict[str, Any],
    file_path_str: str,
    *,
    max_entity_value_length: int | None = None,
) -> dict[str, Any]:
    """Return all write-batches for a single file, ready for UNWIND dispatch.

    No Neo4j I/O is performed; this is pure data transformation.

    Args:
        file_data: Parsed file payload.
        file_path_str: Resolved absolute file path string.

    Returns:
        Dict with keys ``entities_by_label``, ``params_rows``,
        ``module_rows``, ``nested_fn_rows``, ``class_fn_rows``,
        ``module_inclusion_rows``, ``js_import_rows``,
        ``generic_import_rows``.
    """
    entities_by_label: dict[str, list[dict[str, Any]]] = {}
    params_rows: list[dict[str, Any]] = []
    module_rows: list[dict[str, Any]] = []
    nested_fn_rows: list[dict[str, Any]] = []
    class_fn_rows: list[dict[str, Any]] = []
    module_inclusion_rows: list[dict[str, Any]] = []
    js_import_rows: list[dict[str, Any]] = []
    generic_import_rows: list[dict[str, Any]] = []

    for field_key, label in ITEM_MAPPINGS_KEYS:
        for item in file_data.get(field_key, []):
            if label == "Function" and "cyclomatic_complexity" not in item:
                item["cyclomatic_complexity"] = 1

            use_uid = label in CONTENT_ENTITY_LABELS and bool(item.get("uid"))
            row = entity_props_for_unwind(
                label,
                item,
                file_path_str,
                use_uid,
                max_entity_value_length=max_entity_value_length,
            )
            entities_by_label.setdefault(label, []).append(row)

            if label == "Function":
                for arg_name in item.get("args", []):
                    params_rows.append(
                        {
                            "func_name": item["name"],
                            "file_path": file_path_str,
                            "line_number": item["line_number"],
                            "arg_name": arg_name,
                        }
                    )

    for module_item in file_data.get("modules", []):
        module_rows.append({"name": module_item["name"], "lang": file_data.get("lang")})

    for item in file_data.get("functions", []):
        if item.get("context_type") == "function_definition":
            nested_fn_rows.append(
                {
                    "context": item["context"],
                    "file_path": file_path_str,
                    "name": item["name"],
                    "line_number": item["line_number"],
                }
            )

    for func in file_data.get("functions", []):
        if func.get("class_context"):
            class_fn_rows.append(
                {
                    "class_name": func["class_context"],
                    "file_path": file_path_str,
                    "func_name": func["name"],
                    "func_line": func["line_number"],
                }
            )

    for inclusion in file_data.get("module_inclusions", []):
        module_inclusion_rows.append(
            {
                "class_name": inclusion["class"],
                "file_path": file_path_str,
                "module_name": inclusion["module"],
            }
        )

    lang = file_data.get("lang")
    for imp in file_data.get("imports", []):
        if lang == "javascript":
            module_name = imp.get("source")
            if not module_name:
                continue
            js_import_rows.append(
                {
                    "file_path": file_path_str,
                    "module_name": module_name,
                    "imported_name": imp.get("name", "*"),
                    "alias": imp.get("alias"),
                    "imp_line": imp.get("line_number"),
                }
            )
        else:
            generic_import_rows.append(
                {
                    "file_path": file_path_str,
                    "module_name": imp.get("name"),
                    "full_import_name": imp.get("full_import_name"),
                    "line_number_rel": imp.get("line_number") or None,
                    "alias_rel": imp.get("alias") or None,
                }
            )

    return {
        "entities_by_label": entities_by_label,
        "params_rows": params_rows,
        "module_rows": module_rows,
        "nested_fn_rows": nested_fn_rows,
        "class_fn_rows": class_fn_rows,
        "module_inclusion_rows": module_inclusion_rows,
        "js_import_rows": js_import_rows,
        "generic_import_rows": generic_import_rows,
    }


def flush_write_batches(
    tx: Any,
    batches: dict[str, Any],
    *,
    info_logger_fn: Any | None = None,
) -> dict[str, dict[str, float | int]]:
    """Flush all accumulated write batches through UNWIND queries.

    Args:
        tx: Neo4j transaction.
        batches: Dict as returned by ``collect_file_write_data`` (with
                 ``entities_by_label`` potentially being a merged accumulation
                 across multiple files).
    """
    batch_metrics: dict[str, dict[str, float | int]] = {}
    telemetry = get_observability()
    for label, rows in batches["entities_by_label"].items():
        summary = _flush_entity_label_batches(
            tx,
            label,
            rows,
            info_logger_fn=info_logger_fn,
        )
        batch_metrics[f"entity:{label}"] = summary
        telemetry.record_graph_write_batch(
            batch_type="entity",
            label=label,
            rows=int(summary["total_rows"]),
            duration_seconds=float(summary["duration_seconds"]),
        )
        if callable(info_logger_fn):
            info_logger_fn(
                f"Graph write batch entity label={label} "
                f"rows={summary['total_rows']} "
                f"uid_rows={summary['uid_rows']} "
                f"name_rows={summary['name_rows']} "
                f"chunks={summary['chunk_count']} "
                f"max_chunk_rows={summary['max_chunk_rows']} "
                f"duration={summary['duration_seconds']:.2f}s"
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
        if callable(info_logger_fn):
            info_logger_fn(
                f"Graph write batch type={batch_name} rows={len(rows)} duration={elapsed:.2f}s"
            )
    return batch_metrics


def has_pending_rows(batches: dict[str, Any]) -> bool:
    """Return whether a write-batch accumulator still has rows to flush."""

    if any(rows for rows in batches["entities_by_label"].values()):
        return True
    return any(batches[key] for key in _NON_ENTITY_BATCH_KEYS)


def pending_row_count(batches: dict[str, Any]) -> int:
    """Return the total number of buffered rows across all batch collections."""

    entity_rows = sum(len(rows) for rows in batches["entities_by_label"].values())
    other_rows = sum(len(batches[key]) for key in _NON_ENTITY_BATCH_KEYS)
    return entity_rows + other_rows


def should_flush_batches(batches: dict[str, Any]) -> bool:
    """Return whether the in-memory write buffer should flush early."""

    return pending_row_count(batches) >= _WRITE_BATCH_FLUSH_ROW_THRESHOLD


def log_prepared_entity_batches(
    batches: dict[str, Any],
    *,
    repo_path_str: str,
    info_logger_fn: Any | None = None,
) -> None:
    """Emit pre-flush entity summaries for the current write accumulator."""

    if not callable(info_logger_fn):
        return
    entity_counts = {
        label: len(rows)
        for label, rows in sorted(batches["entities_by_label"].items())
        if rows
    }
    if not entity_counts:
        return
    entity_summary = ", ".join(
        f"{label}={count}" for label, count in entity_counts.items()
    )
    info_logger_fn(f"Prepared graph entity batches for {repo_path_str}: {entity_summary}")
    for label, rows in sorted(batches["entities_by_label"].items()):
        if len(rows) < _LARGE_LABEL_SUMMARY_THRESHOLD:
            continue
        source_summary = summarize_entity_source_files(
            rows,
            repo_root=repo_path_str,
        )
        top_files = ", ".join(
            f"{path}({count})" for path, count in source_summary["top_files"]
        )
        if not top_files:
            continue
        info_logger_fn(
            f"Prepared graph entity batch detail for {repo_path_str}: "
            f"label={label} files={source_summary['file_count']} "
            f"top_files={top_files}"
        )


def summarize_entity_source_files(
    rows: list[dict[str, Any]],
    *,
    repo_root: str | Path | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Return repo-relative top-file counts for one prepared entity label."""

    file_counts: Counter[str] = Counter()
    resolved_repo_root = Path(repo_root).resolve() if repo_root is not None else None

    for row in rows:
        file_path_value = row.get("file_path")
        if not isinstance(file_path_value, str) or not file_path_value:
            continue
        file_path = Path(file_path_value).resolve()
        display_path: str
        if resolved_repo_root is not None:
            try:
                display_path = file_path.relative_to(resolved_repo_root).as_posix()
            except ValueError:
                display_path = file_path.name
        else:
            display_path = file_path.name
        file_counts[display_path] += 1

    return {
        "file_count": len(file_counts),
        "top_files": file_counts.most_common(limit),
    }


def _flush_entity_label_batches(
    tx: Any,
    label: str,
    rows: list[dict[str, Any]],
    *,
    info_logger_fn: Any | None = None,
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

    chunk_size = _ENTITY_BATCH_SIZE_BY_LABEL.get(label, _DEFAULT_ENTITY_BATCH_SIZE)
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
        debug_logger(
            f"Graph write batch entity start "
            f"label={label} chunk={chunk_number}/{total_chunks} rows={len(chunk)}"
        )
        chunk_summary = run_entity_unwind(tx, label, chunk)
        total_rows += int(chunk_summary["total_rows"])
        uid_rows += int(chunk_summary["uid_rows"])
        name_rows += int(chunk_summary["name_rows"])
        duration_seconds += float(chunk_summary["duration_seconds"])
        chunk_count += 1
        max_chunk_rows = max(max_chunk_rows, len(chunk))
        debug_logger(
            f"Graph write batch entity done "
            f"label={label} chunk={chunk_number}/{total_chunks} "
            f"rows={len(chunk)} duration={float(chunk_summary['duration_seconds']):.2f}s"
        )

    return {
        "total_rows": total_rows,
        "uid_rows": uid_rows,
        "name_rows": name_rows,
        "duration_seconds": duration_seconds,
        "chunk_count": chunk_count,
        "max_chunk_rows": max_chunk_rows,
    }


def merge_batches(
    accumulator: dict[str, Any],
    new_batches: dict[str, Any],
) -> None:
    """Merge ``new_batches`` in-place into ``accumulator``.

    Args:
        accumulator: Target dict (modified in-place).
        new_batches: Source dict produced by ``collect_file_write_data``.
    """
    for label, rows in new_batches["entities_by_label"].items():
        accumulator["entities_by_label"].setdefault(label, []).extend(rows)
    accumulator["params_rows"].extend(new_batches["params_rows"])
    accumulator["module_rows"].extend(new_batches["module_rows"])
    accumulator["nested_fn_rows"].extend(new_batches["nested_fn_rows"])
    accumulator["class_fn_rows"].extend(new_batches["class_fn_rows"])
    accumulator["module_inclusion_rows"].extend(new_batches["module_inclusion_rows"])
    accumulator["js_import_rows"].extend(new_batches["js_import_rows"])
    accumulator["generic_import_rows"].extend(new_batches["generic_import_rows"])


def empty_accumulator() -> dict[str, Any]:
    """Return an empty write-batch accumulator."""
    return {
        "entities_by_label": {},
        "params_rows": [],
        "module_rows": [],
        "nested_fn_rows": [],
        "class_fn_rows": [],
        "module_inclusion_rows": [],
        "js_import_rows": [],
        "generic_import_rows": [],
    }


__all__ = [
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
