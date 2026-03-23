"""Function-call relationship helpers for ``GraphBuilder``."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

_CALL_RELATIONSHIP_BATCH_SIZE = 250


def safe_run_create(session: Any, query: str, params: dict[str, Any]) -> bool:
    """Run a relationship creation query and report whether it created a row."""
    try:
        result = session.run(query, params)
        row = result.single()
        return row is not None and row.get("created", 0) > 0
    except Exception:
        return False


def create_function_calls(
    builder: Any,
    session: Any,
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    get_config_value_fn: Any,
    warning_logger_fn: Any,
) -> None:
    """Create ``CALLS`` relationships for one parsed file."""
    caller_file_path = str(Path(file_data["path"]).resolve())
    num_calls = len(file_data.get("function_calls", []))
    if num_calls > 0:
        debug_log_fn(
            f"Creating function calls for {caller_file_path} (Count: {num_calls})"
        )

    contextual_rows, file_level_rows, _ = _prepare_call_rows(
        file_data,
        imports_map,
        caller_file_path=caller_file_path,
        get_config_value_fn=get_config_value_fn,
        warning_logger_fn=warning_logger_fn,
        start_row_id=0,
    )
    _create_contextual_call_relationships_batched(session, contextual_rows)
    _create_file_level_call_relationships_batched(session, file_level_rows)


def create_all_function_calls(
    builder: Any,
    all_file_data: list[dict[str, Any]],
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    get_config_value_fn: Any | None = None,
    warning_logger_fn: Any | None = None,
) -> dict[str, float | int]:
    """Create ``CALLS`` relationships after all files are indexed."""
    debug_log_fn(f"_create_all_function_calls called with {len(all_file_data)} files")
    resolved_get_config_value_fn = get_config_value_fn or (lambda _key: None)
    resolved_warning_logger_fn = warning_logger_fn or (lambda *_args, **_kwargs: None)
    contextual_rows: list[dict[str, Any]] = []
    file_level_rows: list[dict[str, Any]] = []
    next_row_id = 0
    for index, file_data in enumerate(all_file_data):
        debug_log_fn(
            f"Processing file {index + 1}/{len(all_file_data)}: {file_data.get('path', 'unknown')}"
        )
        caller_file_path = str(Path(file_data["path"]).resolve())
        file_contextual_rows, file_level_batch_rows, next_row_id = _prepare_call_rows(
            file_data,
            imports_map,
            caller_file_path=caller_file_path,
            get_config_value_fn=resolved_get_config_value_fn,
            warning_logger_fn=resolved_warning_logger_fn,
            start_row_id=next_row_id,
        )
        contextual_rows.extend(file_contextual_rows)
        file_level_rows.extend(file_level_batch_rows)

    with builder.driver.session() as session:
        contextual_metrics = _create_contextual_call_relationships_batched(
            session, contextual_rows
        )
        file_level_metrics = _create_file_level_call_relationships_batched(
            session, file_level_rows
        )
    metrics = _combine_call_relationship_metrics(contextual_metrics, file_level_metrics)
    setattr(builder, "_last_call_relationship_metrics", metrics)
    debug_log_fn(
        "CALLS metrics: "
        f"contextual_exact={metrics['contextual_exact_duration_seconds']:.1f}s, "
        f"contextual_fallback={metrics['contextual_fallback_duration_seconds']:.1f}s, "
        f"file_level_exact={metrics['file_level_exact_duration_seconds']:.1f}s, "
        f"file_level_fallback={metrics['file_level_fallback_duration_seconds']:.1f}s, "
        f"total={metrics['total_duration_seconds']:.1f}s"
    )
    return metrics


def _prepare_call_rows(
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
    *,
    caller_file_path: str,
    get_config_value_fn: Any,
    warning_logger_fn: Any,
    start_row_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Resolve one file's calls into contextual and file-level batch rows."""

    local_names = {f["name"] for f in file_data.get("functions", [])} | {
        c["name"] for c in file_data.get("classes", [])
    }
    local_imports = {
        imp.get("alias") or imp["name"].split(".")[-1]: imp["name"]
        for imp in file_data.get("imports", [])
    }
    skip_external = (
        get_config_value_fn("SKIP_EXTERNAL_RESOLUTION") or "false"
    ).lower() == "true"
    contextual_rows: list[dict[str, Any]] = []
    file_level_rows: list[dict[str, Any]] = []
    next_row_id = start_row_id

    for call in file_data.get("function_calls", []):
        called_name = call["name"]
        if called_name in __builtins__:
            continue

        resolved_path = None
        full_call = call.get("full_name", called_name)
        base_obj = full_call.split(".")[0] if "." in full_call else None
        is_chained_call = full_call.count(".") > 1 if "." in full_call else False

        if is_chained_call and base_obj in (
            "self",
            "this",
            "super",
            "super()",
            "cls",
            "@",
        ):
            lookup_name = called_name
        else:
            lookup_name = base_obj if base_obj else called_name

        if (
            base_obj in ("self", "this", "super", "super()", "cls", "@")
            and not is_chained_call
        ):
            resolved_path = caller_file_path
        elif lookup_name in local_names:
            resolved_path = caller_file_path
        elif call.get("inferred_obj_type"):
            obj_type = call["inferred_obj_type"]
            possible_paths = imports_map.get(obj_type, [])
            if len(possible_paths) > 0:
                resolved_path = possible_paths[0]

        if not resolved_path:
            possible_paths = imports_map.get(lookup_name, [])
            if len(possible_paths) == 1:
                resolved_path = possible_paths[0]
            elif len(possible_paths) > 1 and lookup_name in local_imports:
                if direct_paths := _direct_import_paths(
                    imports_map, lookup_name, local_imports
                ):
                    resolved_path = direct_paths[0]
                else:
                    resolved_path = _match_import_path(
                        local_imports[lookup_name], possible_paths
                    )

        if not resolved_path:
            if not skip_external:
                warning_logger_fn(
                    f"Could not resolve call {called_name} (lookup: {lookup_name}) in {caller_file_path}"
                )
            is_unresolved_external = True
        else:
            is_unresolved_external = False

        if not resolved_path and called_name in local_names:
            resolved_path = caller_file_path
            is_unresolved_external = False
        elif (
            not resolved_path
            and called_name in imports_map
            and imports_map[called_name]
        ):
            resolved_path = _resolve_from_import_candidates(
                called_name, imports_map, local_imports
            )
        elif not resolved_path:
            resolved_path = caller_file_path

        if skip_external and is_unresolved_external:
            continue

        call_params = _build_call_params(
            call, caller_file_path, called_name, resolved_path
        )
        call_params["row_id"] = next_row_id
        next_row_id += 1
        caller_context = call.get("context")
        if (
            caller_context
            and len(caller_context) == 3
            and caller_context[0] is not None
        ):
            contextual_rows.append(
                {
                    **call_params,
                    "caller_name": caller_context[0],
                }
            )
        else:
            file_level_rows.append(call_params)

    return contextual_rows, file_level_rows, next_row_id


def name_from_symbol(symbol: str) -> str:
    """Extract a readable symbol name from a SCIP symbol identifier."""
    stripped = symbol.rstrip(".#")
    stripped = re.sub(r"\(\)\.?$", "", stripped)
    parts = re.split(r"[/#]", stripped)
    last = parts[-1] if parts else symbol
    return last or symbol


def _direct_import_paths(
    imports_map: dict[str, Any], lookup_name: str, local_imports: dict[str, str]
) -> list[str]:
    """Return direct import match candidates when a local alias is available."""
    full_import_name = local_imports[lookup_name]
    return imports_map.get(full_import_name, [])


def _match_import_path(full_import_name: str, possible_paths: list[str]) -> str | None:
    """Return the first path that matches the dotted import path."""
    for path in possible_paths:
        if full_import_name.replace(".", "/") in path:
            return path
    return None


def _resolve_from_import_candidates(
    called_name: str,
    imports_map: dict[str, Any],
    local_imports: dict[str, str],
) -> str | None:
    """Choose the best path candidate for an imported symbol."""
    candidates = imports_map[called_name]
    for path in candidates:
        for import_name in local_imports.values():
            if import_name.replace(".", "/") in path:
                return path
    return candidates[0] if candidates else None


def _build_call_params(
    call: dict[str, Any],
    caller_file_path: str,
    called_name: str,
    resolved_path: str,
) -> dict[str, Any]:
    """Build the common query parameters for function call relationships."""
    return {
        "caller_file_path": caller_file_path,
        "called_name": called_name,
        "called_file_path": resolved_path,
        "line_number": call["line_number"],
        "args": call.get("args", []),
        "full_call_name": call.get("full_name", called_name),
    }


def _create_contextual_call_relationships_batched(
    session: Any,
    rows: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Create contextual call relationships in batched UNWIND passes."""

    return _create_call_relationships_batched(
        session,
        rows,
        exact_queries=_contextual_call_batch_queries(),
        fallback_query=_contextual_call_fallback_batch_query(),
    )


def _create_file_level_call_relationships_batched(
    session: Any,
    rows: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Create file-level call relationships in batched UNWIND passes."""

    return _create_call_relationships_batched(
        session,
        rows,
        exact_queries=_file_level_call_batch_queries(),
        fallback_query=_file_level_call_fallback_batch_query(),
    )


def _create_call_relationships_batched(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    exact_queries: tuple[str, ...],
    fallback_query: str,
) -> dict[str, float | int]:
    """Create call relationships via exact queries followed by one fallback."""

    exact_started = time.monotonic()
    remaining_rows = rows
    for query in exact_queries:
        remaining_rows = _run_call_batch_query(session, query, remaining_rows)
        if not remaining_rows:
            return _call_resolution_metrics(
                rows=rows,
                fallback_rows=0,
                unresolved_rows=[],
                exact_duration=time.monotonic() - exact_started,
                fallback_duration=0.0,
            )
    exact_duration = time.monotonic() - exact_started
    fallback_rows = len(remaining_rows)
    fallback_started = time.monotonic()
    unresolved_rows = _run_call_batch_query(session, fallback_query, remaining_rows)
    return _call_resolution_metrics(
        rows=rows,
        fallback_rows=fallback_rows,
        unresolved_rows=unresolved_rows,
        exact_duration=exact_duration,
        fallback_duration=time.monotonic() - fallback_started,
    )


def _call_resolution_metrics(
    *,
    rows: list[dict[str, Any]],
    fallback_rows: int,
    unresolved_rows: list[dict[str, Any]],
    exact_duration: float,
    fallback_duration: float,
) -> dict[str, float | int]:
    """Return a normalized metric payload for one batched call-resolution pass."""

    return {
        "rows": len(rows),
        "fallback_rows": fallback_rows,
        "unmatched_rows": len(unresolved_rows),
        "exact_duration_seconds": exact_duration,
        "fallback_duration_seconds": fallback_duration,
    }


def _combine_call_relationship_metrics(
    contextual_metrics: dict[str, float | int],
    file_level_metrics: dict[str, float | int],
) -> dict[str, float | int]:
    """Combine contextual and file-level timing metrics under stable keys."""

    metrics = {
        **{f"contextual_{key}": value for key, value in contextual_metrics.items()},
        **{f"file_level_{key}": value for key, value in file_level_metrics.items()},
    }
    metrics["exact_duration_seconds"] = (
        metrics["contextual_exact_duration_seconds"]
        + metrics["file_level_exact_duration_seconds"]
    )
    metrics["fallback_duration_seconds"] = (
        metrics["contextual_fallback_duration_seconds"]
        + metrics["file_level_fallback_duration_seconds"]
    )
    metrics["total_duration_seconds"] = (
        metrics["exact_duration_seconds"] + metrics["fallback_duration_seconds"]
    )
    return metrics


def _run_call_batch_query(
    session: Any,
    query: str,
    rows: list[dict[str, Any]],
    *,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Run one batched call-link query and return the unresolved rows."""

    if not rows:
        return []
    unresolved_rows: list[dict[str, Any]] = []
    effective_batch_size = max(
        1,
        batch_size if batch_size is not None else _CALL_RELATIONSHIP_BATCH_SIZE,
    )
    for start in range(0, len(rows), effective_batch_size):
        chunk = rows[start : start + effective_batch_size]
        try:
            result = session.run(query, {"rows": chunk})
            row = result.single()
        except Exception:
            unresolved_rows.extend(chunk)
            continue
        matched_row_ids = set()
        if row is not None:
            matched_row_ids.update(row.get("matched_row_ids") or [])
        if not matched_row_ids:
            unresolved_rows.extend(chunk)
            continue
        unresolved_rows.extend(
            item for item in chunk if item.get("row_id") not in matched_row_ids
        )
    return unresolved_rows


def _contextual_call_batch_queries() -> tuple[str, ...]:
    """Return ordered batched query attempts for contextual call resolution."""

    return (
        """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller_function:Function {name: row.caller_name, path: row.caller_file_path})
        OPTIONAL MATCH (caller_class:Class {name: row.caller_name, path: row.caller_file_path})
        WITH row, COALESCE(caller_function, caller_class) AS caller
        OPTIONAL MATCH (called_function:Function {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class:Class {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class)-[:CONTAINS]->(init:Function)
        WHERE init.name IN ["__init__", "constructor"]
        WITH row, caller, COALESCE(called_function, init, called_class) AS final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(final_target)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
        """,
    )


def _contextual_call_fallback_batch_query() -> str:
    """Return the batched fallback query for contextual call resolution."""

    return """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller_function:Function {name: row.caller_name, path: row.caller_file_path})
        OPTIONAL MATCH (caller_class:Class {name: row.caller_name, path: row.caller_file_path})
        WITH row, COALESCE(caller_function, caller_class) AS caller
        OPTIONAL MATCH (called:Function {name: row.called_name})
        WITH row, caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(called)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
    """


def _file_level_call_batch_queries() -> tuple[str, ...]:
    """Return ordered batched query attempts for file-level call resolution."""

    return (
        """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller:File {path: row.caller_file_path})
        OPTIONAL MATCH (called_function:Function {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class:Class {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class)-[:CONTAINS]->(init:Function)
        WHERE init.name IN ["__init__", "constructor"]
        WITH row, caller, COALESCE(called_function, init, called_class) AS final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(final_target)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
        """,
    )


def _file_level_call_fallback_batch_query() -> str:
    """Return the batched fallback query for file-level call resolution."""

    return """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller:File {path: row.caller_file_path})
        OPTIONAL MATCH (called:Function {name: row.called_name})
        WITH row, caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(called)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
    """


__all__ = [
    "create_all_function_calls",
    "create_function_calls",
    "name_from_symbol",
    "safe_run_create",
]
