"""File-level graph persistence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...cli.config_manager import get_config_value
from ...observability import get_observability
from ...utils.debug_log import emit_log_call
from .batching import collect_file_write_data, flush_write_batches
from .content_store import content_dual_write
from .repositories import (
    _merge_directory_chain,
    _relative_path_with_fallback,
    _run_write_query,
    collect_directory_chain_rows,
    read_repository_metadata,
)
from .session import begin_transaction
from .unwind import resolve_max_entity_value_length

BeginTransactionFn = Callable[[Any], tuple[Any, bool]]
CollectFileWriteDataFn = Callable[..., dict[str, Any]]
ContentDualWriteFn = Callable[[dict[str, Any], str, dict[str, Any], Any], None]


def write_one_file_graph(
    tx: Any,
    file_data: dict[str, Any],
    *,
    repo_path_obj: Path,
    max_entity_value_length: int,
    warning_logger_fn: Any,
    collect_file_write_data_fn: CollectFileWriteDataFn = collect_file_write_data,
    dir_rows_accumulator: list[dict[str, str]] | None = None,
    containment_rows_accumulator: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Write one file node and return its prepared batch payload."""

    file_path_str = str(Path(file_data["path"]).resolve())
    file_path_obj = Path(file_path_str)
    file_name = Path(file_path_str).name
    is_dependency = file_data.get("is_dependency", False)
    relative_path = _relative_path_with_fallback(
        file_path_obj,
        repo_path_obj,
        warning_logger_fn=warning_logger_fn,
        operation="batch graph persistence",
    ).as_posix()

    _run_write_query(
        tx,
        """
        MERGE (f:File {path: $file_path})
        SET f.name = $name, f.relative_path = $relative_path, f.is_dependency = $is_dependency
        """,
        file_path=file_path_str,
        name=file_name,
        relative_path=relative_path,
        is_dependency=is_dependency,
    )

    if dir_rows_accumulator is not None and containment_rows_accumulator is not None:
        dir_rows, cont_rows = collect_directory_chain_rows(
            file_path_obj,
            repo_path_obj,
            file_path_str,
            warning_logger_fn=warning_logger_fn,
        )
        dir_rows_accumulator.extend(dir_rows)
        containment_rows_accumulator.extend(cont_rows)
    else:
        _merge_directory_chain(
            tx,
            file_path_obj,
            repo_path_obj,
            file_path_str,
            warning_logger_fn=warning_logger_fn,
        )

    return file_path_str, collect_file_write_data_fn(
        file_data,
        file_path_str,
        max_entity_value_length=max_entity_value_length,
    )


def add_file_to_graph(
    builder: Any,
    file_data: dict[str, Any],
    repo_name: str,
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
    content_dual_write_fn: ContentDualWriteFn = content_dual_write,
    begin_transaction_fn: BeginTransactionFn = begin_transaction,
) -> None:
    """Persist a parsed file, its contained nodes, and immediate edges."""

    _ = (repo_name, imports_map, info_logger_fn)
    calls_count = len(file_data.get("function_calls", []))
    emit_log_call(
        debug_log_fn,
        f"Executing add_file_to_graph for {file_data.get('path', 'unknown')} - Calls found: {calls_count}",
        event_name="graph.file.write.started",
        extra_keys={
            "file_path": str(file_data.get("path", "unknown")),
            "function_call_count": calls_count,
        },
    )

    file_path_str = str(Path(file_data["path"]).resolve())
    file_path_obj = Path(file_path_str)
    file_name = Path(file_path_str).name
    is_dependency = file_data.get("is_dependency", False)
    repo_path_obj = Path(file_data["repo_path"]).resolve()

    with builder.driver.session() as session:
        repository = read_repository_metadata(session, repo_path_obj)

        relative_path = _relative_path_with_fallback(
            file_path_obj,
            repo_path_obj,
            warning_logger_fn=warning_logger_fn,
            operation="single-file graph persistence",
        ).as_posix()

        content_dual_write_fn(file_data, file_name, repository, warning_logger_fn)
        max_entity_value_length = resolve_max_entity_value_length(
            get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
        )

        tx, is_explicit = begin_transaction_fn(session)
        try:
            with get_observability().start_span(
                "pcg.graph.file_commit",
                attributes={
                    "pcg.graph.file_path": file_path_str,
                    "pcg.graph.repo_path": str(repo_path_obj),
                },
            ):
                _run_write_query(
                    tx,
                    """
                    MERGE (f:File {path: $file_path})
                    SET f.name = $name, f.relative_path = $relative_path, f.is_dependency = $is_dependency
                    """,
                    file_path=file_path_str,
                    name=file_name,
                    relative_path=relative_path,
                    is_dependency=is_dependency,
                )

                _merge_directory_chain(
                    tx,
                    file_path_obj,
                    repo_path_obj,
                    file_path_str,
                    warning_logger_fn=warning_logger_fn,
                )

                write_data = collect_file_write_data(
                    file_data,
                    file_path_str,
                    max_entity_value_length=max_entity_value_length,
                )
                flush_write_batches(tx, write_data)

                if is_explicit:
                    tx.commit()
        except Exception:
            if is_explicit:
                tx.rollback()
            raise


__all__ = ["add_file_to_graph", "write_one_file_graph"]
