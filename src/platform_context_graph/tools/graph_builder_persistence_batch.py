"""Batch data collection and lifecycle helpers for cross-file Neo4j writes."""

from __future__ import annotations

from typing import Any

from ..content.ingest import CONTENT_ENTITY_LABELS
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
) -> None:
    """Flush all accumulated write batches through UNWIND queries.

    Args:
        tx: Neo4j transaction.
        batches: Dict as returned by ``collect_file_write_data`` (with
                 ``entities_by_label`` potentially being a merged accumulation
                 across multiple files).
    """
    for label, rows in batches["entities_by_label"].items():
        run_entity_unwind(tx, label, rows)

    run_parameter_unwind(tx, batches["params_rows"])
    run_module_unwind(tx, batches["module_rows"])
    run_nested_function_unwind(tx, batches["nested_fn_rows"])
    run_class_function_unwind(tx, batches["class_fn_rows"])
    run_module_inclusion_unwind(tx, batches["module_inclusion_rows"])
    run_js_import_unwind(tx, batches["js_import_rows"])
    run_generic_import_unwind(tx, batches["generic_import_rows"])


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
    "merge_batches",
]
