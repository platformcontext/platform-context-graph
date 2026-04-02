"""Batch data collection and lifecycle helpers for cross-file graph writes."""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import time
from typing import Any

from ...content.ingest import CONTENT_ENTITY_LABELS
from ...utils.debug_log import emit_log_call
from .unwind import (
    ITEM_MAPPINGS_KEYS,
    entity_props_for_unwind,
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

    _skip_variables = os.environ.get("INDEX_VARIABLES", "true").lower() == "false"

    for field_key, label in ITEM_MAPPINGS_KEYS:
        if _skip_variables and label == "Variable":
            continue
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

def should_flush_batches(
    batches: dict[str, Any],
    flush_threshold: int | None = None,
) -> bool:
    """Return whether the in-memory write buffer should flush early."""
    threshold = (
        flush_threshold if flush_threshold is not None
        else _WRITE_BATCH_FLUSH_ROW_THRESHOLD
    )
    return pending_row_count(batches) >= threshold

def log_prepared_entity_batches(
    batches: dict[str, Any],
    *,
    repo_path_str: str,
    info_logger_fn: Any | None = None,
    debug_logger_fn: Any | None = None,
) -> None:
    """Emit pre-flush entity summaries for the current write accumulator."""

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
    if callable(info_logger_fn):
        emit_log_call(
            info_logger_fn,
            f"Graph entity batch ready for {repo_path_str}: {entity_summary}",
            event_name="graph.batch.prepared",
            extra_keys={
                "repo_path": repo_path_str,
                "entity_counts": entity_counts,
            },
        )
    elif callable(debug_logger_fn):
        emit_log_call(
            debug_logger_fn,
            f"Prepared graph entity batches for {repo_path_str}: {entity_summary}",
            event_name="graph.batch.prepared",
            extra_keys={
                "repo_path": repo_path_str,
                "entity_counts": entity_counts,
            },
        )
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
        emit_log_call(
            debug_logger_fn,
            f"Prepared graph entity batch detail for {repo_path_str}: "
            f"label={label} files={source_summary['file_count']} "
            f"top_files={top_files}",
            event_name="graph.batch.prepared_detail",
            extra_keys={
                "repo_path": repo_path_str,
                "label": label,
                "file_count": source_summary["file_count"],
                "top_files": [
                    {"path": path, "count": count}
                    for path, count in source_summary["top_files"]
                ],
            },
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
    "_DEFAULT_ENTITY_BATCH_SIZE",
    "_ENTITY_BATCH_SIZE_BY_LABEL",
    "_LARGE_LABEL_SUMMARY_THRESHOLD",
    "_NON_ENTITY_BATCH_KEYS",
    "_WRITE_BATCH_FLUSH_ROW_THRESHOLD",
    "collect_file_write_data",
    "empty_accumulator",
    "has_pending_rows",
    "log_prepared_entity_batches",
    "merge_batches",
    "pending_row_count",
    "should_flush_batches",
    "summarize_entity_source_files",
]
