"""Persistence helpers for repository and file graph updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..cli.config_manager import get_config_value
from ..content.ingest import prepare_content_entries
from ..content.state import get_postgres_content_provider
from ..observability import get_observability
from ..utils.debug_log import emit_log_call
from .graph_builder_persistence_batch import (
    collect_file_write_data,
    empty_accumulator,
    flush_write_batches,
    has_pending_rows,
    log_prepared_entity_batches,
    merge_batches,
    should_flush_batches,
)
from .graph_builder_persistence_helpers import (
    _bounded_positive_int_config,
    _merge_directory_chain,
    _relative_path_with_fallback,
    _run_managed_write,
    _run_write_query,
    add_repository_to_graph,
    read_repository_metadata,
)
from .graph_builder_persistence_unwind import resolve_max_entity_value_length


@dataclass(frozen=True)
class BatchCommitResult:
    """Describe which files committed successfully in one batch write attempt."""

    committed_file_paths: tuple[str, ...] = ()
    failed_file_paths: tuple[str, ...] = ()

    @property
    def committed_file_count(self) -> int:
        """Return the number of files that reached durable graph state."""

        return len(self.committed_file_paths)

    @property
    def last_committed_file(self) -> str | None:
        """Return the final committed file path when any succeeded."""

        if not self.committed_file_paths:
            return None
        return self.committed_file_paths[-1]


def _content_dual_write(
    file_data: dict[str, Any],
    file_name: str,
    repository: dict[str, Any],
    warning_logger_fn: Any,
) -> None:
    """Attempt a Postgres content-store dual-write for one file."""

    content_provider = get_postgres_content_provider()
    if content_provider is None or not content_provider.enabled:
        return
    telemetry = get_observability()
    try:
        with telemetry.start_span(
            "pcg.content.dual_write",
            attributes={
                "pcg.content.repo_id": repository.get("id"),
                "pcg.content.relative_path": str(file_data.get("path", file_name)),
            },
        ):
            file_entry, entity_entries = prepare_content_entries(
                file_data=file_data,
                repository=repository,
            )
            if file_entry is not None:
                content_provider.upsert_file(file_entry)
            if entity_entries:
                content_provider.upsert_entities(entity_entries)
    except Exception as exc:
        emit_log_call(
            warning_logger_fn,
            f"Content store dual-write failed for {file_name}: {exc}",
            event_name="content.dual_write.failed",
            extra_keys={
                "file_name": file_name,
                "repo_id": repository.get("id"),
            },
            exc_info=exc,
        )

def _begin_transaction(session: Any) -> tuple[Any, bool]:
    """Begin an explicit transaction if the backend supports it.

    Returns:
        Tuple of ``(tx, is_explicit)`` where ``tx`` is a transaction object
        (or the session itself for backends without transaction support) and
        ``is_explicit`` indicates whether ``commit()``/``rollback()`` should
        be called.
    """
    begin = getattr(session, "begin_transaction", None)
    if begin is not None:
        try:
            return begin(), True
        except (AttributeError, NotImplementedError, RuntimeError, TypeError):
            pass
    return session, False


def _write_one_file_graph(
    tx: Any,
    file_data: dict[str, Any],
    *,
    repo_path_obj: Path,
    max_entity_value_length: int,
    warning_logger_fn: Any,
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

    _merge_directory_chain(
        tx,
        file_path_obj,
        repo_path_obj,
        file_path_str,
        warning_logger_fn=warning_logger_fn,
    )

    return file_path_str, collect_file_write_data(
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
) -> None:
    """Persist a parsed file, its contained nodes, and immediate edges.

    Uses a single explicit Neo4j transaction for all write operations and
    UNWIND queries for bulk entity/import operations.

    Args:
        builder: ``GraphBuilder`` facade instance.
        file_data: Parsed file payload emitted by the language parser.
        repo_name: Preserved compatibility argument from the public method signature.
        imports_map: Preserved compatibility argument for public method parity.
        debug_log_fn: Debug logger callable.
        info_logger_fn: Info logger callable.
        warning_logger_fn: Warning logger callable.
    """
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

        # Postgres content dual-write is outside the Neo4j transaction.
        _content_dual_write(file_data, file_name, repository, warning_logger_fn)
        max_entity_value_length = resolve_max_entity_value_length(
            get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
        )

        # All Neo4j writes go inside a single explicit transaction when
        # the backend supports it; otherwise fall back to auto-commit.
        tx, is_explicit = _begin_transaction(session)
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


def commit_file_batch_to_graph(
    builder: Any,
    file_data_list: list[dict[str, Any]],
    repo_path: Path,
    *,
    progress_callback: Any | None = None,
    debug_log_fn: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
) -> BatchCommitResult:
    """Persist a batch of parsed files using bounded Neo4j write transactions.

    Opens one session, reads repository metadata once, then writes the batch in
    smaller transaction-sized file chunks so large repositories do not retain
    one giant in-flight transaction. Postgres content writes are handled
    per-file outside the Neo4j transaction.

    Args:
        builder: ``GraphBuilder`` facade instance.
        file_data_list: List of parsed file payloads to persist.
        repo_path: Resolved repository root path.
        debug_log_fn: Debug logger callable.
        info_logger_fn: Info logger callable.
        warning_logger_fn: Warning logger callable.
    """
    if not file_data_list:
        return BatchCommitResult()

    repo_path_obj = repo_path.resolve()
    repo_path_str = str(repo_path_obj)

    emit_log_call(
        debug_log_fn,
        f"commit_file_batch_to_graph: {len(file_data_list)} files for {repo_path_str}",
        event_name="graph.batch.commit.started",
        extra_keys={
            "repo_path": repo_path_str,
            "file_count": len(file_data_list),
        },
    )
    max_entity_value_length = resolve_max_entity_value_length(
        get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
    )
    tx_file_limit = _bounded_positive_int_config(
        "PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE",
        5,
        maximum=max(1, len(file_data_list)),
    )

    with builder.driver.session() as session:
        repository = read_repository_metadata(session, repo_path_obj)
        total_files = len(file_data_list)
        committed_files = 0
        committed_file_paths: list[str] = []

        for start in range(0, total_files, tx_file_limit):
            tx_chunk = file_data_list[start : start + tx_file_limit]
            for file_data in tx_chunk:
                file_name = Path(file_data["path"]).name
                _content_dual_write(file_data, file_name, repository, warning_logger_fn)

            tx, is_explicit = _begin_transaction(session)
            chunk_file_paths: list[str] = []
            try:
                with get_observability().start_span(
                    "pcg.graph.commit_chunk",
                    attributes={
                        "pcg.graph.repo_path": repo_path_str,
                        "pcg.graph.chunk_file_count": len(tx_chunk),
                    },
                ):
                    accumulator = empty_accumulator()

                    for chunk_index, file_data in enumerate(tx_chunk, start=1):
                        file_path_str, file_batches = _write_one_file_graph(
                            tx,
                            file_data,
                            max_entity_value_length=max_entity_value_length,
                            repo_path_obj=repo_path_obj,
                            warning_logger_fn=warning_logger_fn,
                        )
                        chunk_file_paths.append(file_path_str)
                        merge_batches(accumulator, file_batches)
                        if callable(progress_callback):
                            progress_callback(
                                processed_files=committed_files + chunk_index,
                                total_files=total_files,
                                current_file=file_path_str,
                                committed=False,
                            )
                        if should_flush_batches(accumulator):
                            log_prepared_entity_batches(
                                accumulator,
                                repo_path_str=repo_path_str,
                                info_logger_fn=info_logger_fn,
                                debug_logger_fn=debug_log_fn,
                            )
                            flush_write_batches(
                                tx,
                                accumulator,
                                info_logger_fn=info_logger_fn,
                                debug_logger_fn=debug_log_fn,
                            )
                            accumulator = empty_accumulator()

                    if has_pending_rows(accumulator):
                        log_prepared_entity_batches(
                            accumulator,
                            repo_path_str=repo_path_str,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        flush_write_batches(
                            tx,
                            accumulator,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                    if is_explicit:
                        tx.commit()
            except Exception as exc:
                if is_explicit:
                    tx.rollback()
                emit_log_call(
                    warning_logger_fn,
                    (
                        f"Graph batch chunk failed for {repo_path_str}; "
                        "retrying files individually"
                    ),
                    event_name="graph.batch.commit.chunk_retry",
                    extra_keys={
                        "repo_path": repo_path_str,
                        "chunk_file_count": len(tx_chunk),
                    },
                    exc_info=exc,
                )
                failed_file_paths: list[str] = []
                for file_data in tx_chunk:
                    tx, is_explicit = _begin_transaction(session)
                    try:
                        file_path_str, file_batches = _write_one_file_graph(
                            tx,
                            file_data,
                            max_entity_value_length=max_entity_value_length,
                            repo_path_obj=repo_path_obj,
                            warning_logger_fn=warning_logger_fn,
                        )
                        log_prepared_entity_batches(
                            file_batches,
                            repo_path_str=repo_path_str,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        flush_write_batches(
                            tx,
                            file_batches,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        if is_explicit:
                            tx.commit()
                        committed_files += 1
                        committed_file_paths.append(file_path_str)
                    except Exception as file_exc:
                        if is_explicit:
                            tx.rollback()
                        failed_path = str(Path(file_data["path"]).resolve())
                        failed_file_paths.append(failed_path)
                        emit_log_call(
                            warning_logger_fn,
                            f"Graph file write failed during fallback for {failed_path}",
                            event_name="graph.batch.commit.file_failed",
                            extra_keys={
                                "repo_path": repo_path_str,
                                "file_path": failed_path,
                            },
                            exc_info=file_exc,
                        )
                if failed_file_paths:
                    return BatchCommitResult(
                        committed_file_paths=tuple(committed_file_paths),
                        failed_file_paths=tuple(failed_file_paths),
                    )
                if callable(progress_callback) and tx_chunk:
                    progress_callback(
                        processed_files=committed_files,
                        total_files=total_files,
                        current_file=committed_file_paths[-1],
                        committed=True,
                    )
                continue

            committed_files += len(tx_chunk)
            committed_file_paths.extend(chunk_file_paths)
            if callable(progress_callback) and tx_chunk:
                progress_callback(
                    processed_files=committed_files,
                    total_files=total_files,
                    current_file=str(Path(tx_chunk[-1]["path"]).resolve()),
                    committed=True,
                )
        return BatchCommitResult(committed_file_paths=tuple(committed_file_paths))


__all__ = [
    "BatchCommitResult",
    "add_file_to_graph",
    "add_repository_to_graph",
    "commit_file_batch_to_graph",
]
