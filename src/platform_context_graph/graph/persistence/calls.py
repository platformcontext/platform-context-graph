"""Function-call relationship helpers for ``GraphBuilder``.

Orchestrates CALLS-edge creation across all indexed files.  Row
preparation (import resolution, builtin filtering, pre-filtering) is
delegated to :mod:`.call_row_prep`; batch persistence to
:mod:`.call_batches`.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

from .call_batches import (
    call_resolution_metrics as _call_resolution_metrics,
    combine_call_relationship_metrics as _combine_call_relationship_metrics,
    contextual_call_batch_queries as _contextual_call_batch_queries,
    contextual_repo_scoped_batch_query as _contextual_repo_scoped_batch_query,
    create_contextual_call_relationships_batched as _create_contextual_call_relationships_batched,
    create_file_level_call_relationships_batched as _create_file_level_call_relationships_batched,
    file_level_call_batch_queries as _file_level_call_batch_queries,
    file_level_repo_scoped_batch_query as _file_level_repo_scoped_batch_query,
    filter_fallback_candidate_rows as _filter_fallback_candidate_rows,  # noqa: F401
    run_call_batch_query as _run_call_batch_query_impl,
)
from .call_otel import (
    emit_call_resolution_otel_metrics as _emit_call_resolution_otel_metrics,
)
from .call_prefilter import (
    build_known_callable_names as _build_known_callable_names_flat,  # noqa: F401
    build_known_callable_names_by_family as _build_known_callable_names_by_family,
    compatible_languages,
    max_calls_for_repo_class,
)
from .call_row_prep import (
    is_minified_or_bundled as _is_minified_or_bundled,
    prepare_call_rows as _prepare_call_rows,
)

_CALL_RELATIONSHIP_BUFFER_FLUSH_ROWS = 2000
_CALL_RELATIONSHIP_BATCH_SIZE = 250
_MAX_CALLS_PER_FILE = int(os.environ.get("PCG_MAX_CALLS_PER_FILE", "50"))


def safe_run_create(session: Any, query: str, params: dict[str, Any]) -> bool:
    """Run a relationship creation query and report whether it created a row.

    Args:
        session: Active Neo4j session.
        query: Cypher query containing a ``RETURN ... AS created`` clause.
        params: Query parameters dict.

    Returns:
        ``True`` when the query returned at least one row with
        ``created > 0``, ``False`` otherwise (including on exception).
    """
    try:
        row = session.run(query, params).single()
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
    """Create ``CALLS`` relationships for one parsed file.

    Args:
        builder: ``GraphBuilder`` instance (unused but kept for API
            symmetry with bulk callers).
        session: Active Neo4j session.
        file_data: Parsed file dict with ``path``, ``function_calls``,
            ``functions``, ``classes``, and ``imports`` keys.
        imports_map: Global symbol-to-paths mapping.
        debug_log_fn: Debug-level logging callable.
        get_config_value_fn: Config lookup callable.
        warning_logger_fn: Warning-level logging callable.
    """
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
    all_file_data: list[dict[str, Any]] | Any,
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    get_config_value_fn: Any | None = None,
    warning_logger_fn: Any | None = None,
    progress_callback: Any | None = None,
    repo_class: str | None = None,
) -> dict[str, float | int]:
    """Create ``CALLS`` relationships after all files are indexed.

    Iterates every file in *all_file_data*, prepares call rows via
    :func:`.call_row_prep.prepare_call_rows`, buffers them, and flushes
    in batches to Neo4j.  Emits OTEL metrics and logs aggregated
    prefilter / unresolved statistics on completion.

    Args:
        builder: ``GraphBuilder`` instance (provides ``driver``).
        all_file_data: Iterable of parsed file dicts.
        imports_map: Global symbol-to-paths mapping.
        debug_log_fn: Debug-level logging callable.
        get_config_value_fn: Config lookup callable (optional).
        warning_logger_fn: Warning-level logging callable (optional).
        progress_callback: Optional callable invoked after each file
            with ``current_file``, ``processed_files``, and
            ``total_files`` keyword arguments.
        repo_class: Repository classification string used for adaptive
            per-file call caps when the guardrail is enabled.

    Returns:
        Combined call-resolution metrics dict.
    """
    file_count = len(all_file_data) if hasattr(all_file_data, "__len__") else None
    if file_count is None:
        debug_log_fn("_create_all_function_calls called with streamed file data")
    else:
        debug_log_fn(f"_create_all_function_calls called with {file_count} files")
    resolved_get_config_value_fn = get_config_value_fn or (lambda _key: None)
    resolved_warning_logger_fn = warning_logger_fn or (lambda *_args, **_kwargs: None)

    # Determine effective per-file cap (adaptive or env-based).
    adaptive_enabled = (
        os.environ.get("PCG_ADAPTIVE_RESOLUTION_GUARDRAILS_ENABLED", "false").lower()
        == "true"
    )
    if adaptive_enabled and repo_class:
        effective_cap = max_calls_for_repo_class(repo_class)
        _logger.info(
            "Adaptive resolution: repo_class=%s, max_calls_per_file=%d",
            repo_class,
            effective_cap,
        )
    else:
        effective_cap = _MAX_CALLS_PER_FILE

    next_row_id = 0
    processed_files = 0
    unresolved_counter: Counter[str] = Counter()
    prefiltered_counter: Counter[str] = Counter()
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
        """Persist buffered contextual call rows and reset the buffer."""

        nonlocal contextual_buffer
        if not contextual_buffer:
            return
        _accumulate_resolution_metrics(
            contextual_metrics,
            _create_contextual_call_relationships_batched(session, contextual_buffer),
        )
        contextual_buffer = []

    def _flush_file_level(session: Any) -> None:
        """Persist buffered file-level fallback rows and reset the buffer."""

        nonlocal file_level_buffer
        if not file_level_buffer:
            return
        _accumulate_resolution_metrics(
            file_level_metrics,
            _create_file_level_call_relationships_batched(session, file_level_buffer),
        )
        file_level_buffer = []

    with builder.driver.session() as session:
        # Build family-aware known-callable name set for pre-filtering.
        known_names_by_family = _build_known_callable_names_by_family(session)
        total_names = sum(len(v) for v in known_names_by_family.values())
        debug_log_fn(
            f"Known callable names by family: "
            f"{len(known_names_by_family)} langs, {total_names} names"
        )

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
                    known_callable_names_by_family=known_names_by_family,
                    unresolved_counter=unresolved_counter,
                    prefiltered_counter=prefiltered_counter,
                )
            )
            total_rows = len(file_contextual_rows) + len(file_level_batch_rows)
            if total_rows > effective_cap:
                file_contextual_rows = file_contextual_rows[:effective_cap]
                file_level_batch_rows = file_level_batch_rows[
                    : max(0, effective_cap - len(file_contextual_rows))
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

    # Aggregated prefiltered summary (Fix 3: family-aware prefilter stats).
    if prefiltered_counter:
        total_prefiltered = sum(prefiltered_counter.values())
        lang_fmt = ", ".join(
            f"{lang}={cnt}" for lang, cnt in prefiltered_counter.most_common(10)
        )
        _logger.info(
            "Prefiltered calls (not in family callable set): total=%d, %s",
            total_prefiltered,
            lang_fmt,
        )
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
    """Add one call-resolution metric payload into a mutable aggregate.

    Args:
        totals: Mutable accumulator dict (modified in place).
        current: Metric payload from one batch write.
    """
    for key, value in current.items():
        if isinstance(value, (int, float)):
            totals[key] = totals.get(key, 0) + value


def name_from_symbol(symbol: str) -> str:
    """Extract a readable symbol name from a SCIP symbol identifier.

    Strips trailing punctuation (``#``, ``.``, ``()``), splits on ``/``
    and ``#`` delimiters, and returns the last segment.

    Args:
        symbol: Raw SCIP symbol string.

    Returns:
        The human-readable short name.
    """
    stripped = symbol.rstrip(".#")
    stripped = re.sub(r"\(\)\.?$", "", stripped)
    parts = re.split(r"[/#]", stripped)
    last = parts[-1] if parts else symbol
    return last or symbol


def _run_call_batch_query(
    session: Any,
    query: str,
    rows: list[dict[str, Any]],
    *,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Run one batched call-link query using the module-level batch size.

    Args:
        session: Active Neo4j session.
        query: Cypher query to execute.
        rows: Call-row dicts to pass as parameters.
        batch_size: Override for
            :data:`_CALL_RELATIONSHIP_BATCH_SIZE`.  ``None`` uses the
            module default.

    Returns:
        List of unmatched row dicts returned by the batch writer.
    """

    effective_batch_size = (
        _CALL_RELATIONSHIP_BATCH_SIZE if batch_size is None else batch_size
    )
    return _run_call_batch_query_impl(
        session,
        query,
        rows,
        batch_size=effective_batch_size,
    )


__all__ = [
    "_contextual_call_batch_queries",
    "_contextual_repo_scoped_batch_query",
    "_file_level_call_batch_queries",
    "_file_level_repo_scoped_batch_query",
    "_prepare_call_rows",
    "compatible_languages",
    "create_all_function_calls",
    "create_function_calls",
    "name_from_symbol",
    "safe_run_create",
]
