"""Function-call relationship helpers for ``GraphBuilder``."""

from __future__ import annotations

import builtins as py_builtins
import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

from .graph_builder_call_otel import (
    emit_call_resolution_otel_metrics as _emit_call_resolution_otel_metrics,
)
from .graph_builder_call_batches import (
    call_resolution_metrics as _call_resolution_metrics,
    combine_call_relationship_metrics as _combine_call_relationship_metrics,
    contextual_call_batch_queries as _contextual_call_batch_queries,
    contextual_repo_scoped_batch_query as _contextual_repo_scoped_batch_query,
    create_contextual_call_relationships_batched as _create_contextual_call_relationships_batched,
    create_file_level_call_relationships_batched as _create_file_level_call_relationships_batched,
    file_level_call_batch_queries as _file_level_call_batch_queries,
    file_level_repo_scoped_batch_query as _file_level_repo_scoped_batch_query,
    filter_fallback_candidate_rows as _filter_fallback_candidate_rows,
    run_call_batch_query as _run_call_batch_query_impl,
)

_CALL_RELATIONSHIP_BUFFER_FLUSH_ROWS = 2000
_CALL_RELATIONSHIP_BATCH_SIZE = 250
_PYTHON_BUILTIN_NAMES = frozenset(dir(py_builtins))

_MINIFIED_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".chunk.js")
_MAX_CALLS_PER_FILE = int(os.environ.get("PCG_MAX_CALLS_PER_FILE", "50"))

# Language families for cross-language call resolution.  Only languages
# within the same family may produce CALLS edges in repo-scoped and
# fallback resolution passes.
_LANGUAGE_FAMILIES: dict[str, str] = {
    "javascript": "js_family",
    "typescript": "js_family",
}


def compatible_languages(lang: str | None) -> list[str]:
    """Return the list of languages compatible with *lang* for call resolution.

    Languages within the same family (e.g. JS/TS) are cross-compatible.
    All other languages resolve only against themselves.

    Args:
        lang: The source language identifier, or ``None``.

    Returns:
        A list of compatible language identifiers.  Empty when *lang*
        is ``None``.
    """
    if not lang:
        return []
    family = _LANGUAGE_FAMILIES.get(lang)
    if family:
        return [k for k, v in _LANGUAGE_FAMILIES.items() if v == family]
    return [lang]


def _is_minified_or_bundled(file_path: str) -> bool:
    """Return whether a file is minified or bundled and should skip call resolution."""

    lower = file_path.lower()
    return any(lower.endswith(suffix) for suffix in _MINIFIED_SUFFIXES)


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


def _build_known_callable_names(session: Any) -> frozenset[str]:
    """Query Neo4j for all distinct Function and Class names."""
    names: set[str] = set()
    for label in ("Function", "Class"):
        rows = session.run(
            f"MATCH (n:{label}) RETURN DISTINCT n.name AS name",
        ).data()
        names.update(row["name"] for row in rows if row.get("name"))
    return frozenset(names)


def create_all_function_calls(
    builder: Any,
    all_file_data: list[dict[str, Any]] | Any,
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    get_config_value_fn: Any | None = None,
    warning_logger_fn: Any | None = None,
    progress_callback: Any | None = None,
) -> dict[str, float | int]:
    """Create ``CALLS`` relationships after all files are indexed."""
    file_count = len(all_file_data) if hasattr(all_file_data, "__len__") else None
    if file_count is None:
        debug_log_fn("_create_all_function_calls called with streamed file data")
    else:
        debug_log_fn(f"_create_all_function_calls called with {file_count} files")
    resolved_get_config_value_fn = get_config_value_fn or (lambda _key: None)
    resolved_warning_logger_fn = warning_logger_fn or (lambda *_args, **_kwargs: None)
    next_row_id = 0
    processed_files = 0
    unresolved_counter: Counter[str] = Counter()
    _empty = dict(
        rows=[],
        fallback_rows=0,
        unresolved_rows=[],
        exact_duration=0.0,
        fallback_duration=0.0,
    )
    contextual_metrics = _call_resolution_metrics(**_empty)
    file_level_metrics = _call_resolution_metrics(**_empty)
    contextual_buffer: list[dict[str, Any]] = []
    file_level_buffer: list[dict[str, Any]] = []

    def _flush_contextual(session: Any) -> None:
        nonlocal contextual_buffer
        if not contextual_buffer:
            return
        _accumulate_resolution_metrics(
            contextual_metrics,
            _create_contextual_call_relationships_batched(session, contextual_buffer),
        )
        contextual_buffer = []

    def _flush_file_level(session: Any) -> None:
        nonlocal file_level_buffer
        if not file_level_buffer:
            return
        _accumulate_resolution_metrics(
            file_level_metrics,
            _create_file_level_call_relationships_batched(session, file_level_buffer),
        )
        file_level_buffer = []

    with builder.driver.session() as session:
        # Build known-callable name set for pre-filtering.
        known_callable_names = _build_known_callable_names(session)
        debug_log_fn(f"Known callable names in graph: {len(known_callable_names)}")

        for file_data in all_file_data:
            processed_files += 1
            file_path_str = file_data.get("path", "")
            if _is_minified_or_bundled(file_path_str):
                continue
            if file_count is None:
                debug_log_fn(
                    "Processing streamed file " f"{processed_files}: {file_path_str}"
                )
            else:
                debug_log_fn(
                    f"Processing file {processed_files}/{file_count}: "
                    f"{file_path_str}"
                )
            caller_file_path = str(Path(file_data["path"]).resolve())
            file_contextual_rows, file_level_batch_rows, next_row_id = (
                _prepare_call_rows(
                    file_data,
                    imports_map,
                    caller_file_path=caller_file_path,
                    get_config_value_fn=resolved_get_config_value_fn,
                    warning_logger_fn=resolved_warning_logger_fn,
                    start_row_id=next_row_id,
                    known_callable_names=known_callable_names,
                    unresolved_counter=unresolved_counter,
                )
            )
            total_rows = len(file_contextual_rows) + len(file_level_batch_rows)
            if total_rows > _MAX_CALLS_PER_FILE:
                file_contextual_rows = file_contextual_rows[:_MAX_CALLS_PER_FILE]
                file_level_batch_rows = file_level_batch_rows[
                    : max(0, _MAX_CALLS_PER_FILE - len(file_contextual_rows))
                ]
            if file_contextual_rows:
                contextual_buffer.extend(file_contextual_rows)
                if len(contextual_buffer) >= _CALL_RELATIONSHIP_BUFFER_FLUSH_ROWS:
                    _flush_contextual(session)
            if file_level_batch_rows:
                file_level_buffer.extend(file_level_batch_rows)
                if len(file_level_buffer) >= _CALL_RELATIONSHIP_BUFFER_FLUSH_ROWS:
                    _flush_file_level(session)
            if callable(progress_callback):
                progress_callback(
                    current_file=caller_file_path,
                    processed_files=processed_files,
                    total_files=file_count,
                )
        _flush_contextual(session)
        _flush_file_level(session)

    # Aggregated unresolved summary (replaces per-call warning spam).
    if unresolved_counter:
        total_unresolved = sum(unresolved_counter.values())
        top_fmt = ", ".join(f"{n}={c}" for n, c in unresolved_counter.most_common(10))
        _logger.info(
            "Unresolved calls: total=%d, distinct=%d, top=[%s]",
            total_unresolved,
            len(unresolved_counter),
            top_fmt,
        )
    metrics = _combine_call_relationship_metrics(contextual_metrics, file_level_metrics)
    setattr(builder, "_last_call_relationship_metrics", metrics)
    debug_log_fn(
        f"CALLS metrics: exact={metrics['exact_duration_seconds']:.1f}s, "
        f"repo_scoped={metrics['repo_scoped_duration_seconds']:.1f}s, "
        f"fallback={metrics['fallback_duration_seconds']:.1f}s, "
        f"total={metrics['total_duration_seconds']:.1f}s"
    )
    _logger.info(
        "CALLS resolution: total=%.1fs, unmatched=%d+%d",
        metrics.get("total_duration_seconds", 0),
        metrics.get("contextual_unmatched_rows", 0),
        metrics.get("file_level_unmatched_rows", 0),
    )
    _emit_call_resolution_otel_metrics(metrics)
    return metrics


def _accumulate_resolution_metrics(
    totals: dict[str, float | int],
    current: dict[str, float | int],
) -> None:
    """Add one call-resolution metric payload into a mutable aggregate."""

    for key, value in current.items():
        if isinstance(value, (int, float)):
            totals[key] = totals.get(key, 0) + value


def _prepare_call_rows(
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
    *,
    caller_file_path: str,
    get_config_value_fn: Any,
    warning_logger_fn: Any,
    start_row_id: int,
    known_callable_names: frozenset[str] | None = None,
    unresolved_counter: Counter | None = None,
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
    repo_path = file_data.get("repo_path", "")
    contextual_rows: list[dict[str, Any]] = []
    file_level_rows: list[dict[str, Any]] = []
    next_row_id = start_row_id

    for call in file_data.get("function_calls", []):
        called_name = call["name"]
        if called_name in _PYTHON_BUILTIN_NAMES:
            continue

        # Name-existence pre-filter: skip calls whose name does not exist
        # as any Function or Class in the graph.
        if known_callable_names is not None and called_name not in known_callable_names:
            if unresolved_counter is not None:
                unresolved_counter[called_name] += 1
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
            is_unresolved_external = True
            if unresolved_counter is not None:
                unresolved_counter[called_name] += 1
            elif not skip_external:
                warning_logger_fn(
                    f"Could not resolve call {called_name} "
                    f"(lookup: {lookup_name}) in {caller_file_path}"
                )
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
            call, caller_file_path, called_name, resolved_path, repo_path
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
    repo_path: str,
) -> dict[str, Any]:
    """Build the common query parameters for function call relationships."""
    lang = call.get("lang")
    return {
        "caller_file_path": caller_file_path,
        "called_name": called_name,
        "called_file_path": resolved_path,
        "line_number": call["line_number"],
        "args": call.get("args", []),
        "full_call_name": call.get("full_name", called_name),
        "lang": lang,
        "compatible_langs": compatible_languages(lang),
        "repo_path": repo_path,
    }


def _run_call_batch_query(
    session: Any,
    query: str,
    rows: list[dict[str, Any]],
    *,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Run one batched call-link query using the module-level batch size."""

    effective_batch_size = (
        _CALL_RELATIONSHIP_BATCH_SIZE if batch_size is None else batch_size
    )
    return _run_call_batch_query_impl(
        session,
        query,
        rows,
        batch_size=effective_batch_size,
    )
