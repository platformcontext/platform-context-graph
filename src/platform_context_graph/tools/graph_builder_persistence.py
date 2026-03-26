"""Persistence helpers for repository and file graph updates."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..cli.config_manager import get_config_value
from ..core.records import record_to_dict
from ..content.ingest import prepare_content_entries, repository_metadata_from_row
from ..observability import get_observability
from ..utils.debug_log import emit_log_call
from ..content.state import get_postgres_content_provider
from .graph_builder_persistence_batch import (
    collect_file_write_data,
    empty_accumulator,
    flush_write_batches,
    has_pending_rows,
    log_prepared_entity_batches,
    merge_batches,
    should_flush_batches,
)
from .graph_builder_persistence_unwind import resolve_max_entity_value_length
def _consume_write_result(result: Any) -> None:
    """Eagerly consume Neo4j write results to release transaction buffers."""

    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()
def _run_write_query(tx_or_session: Any, query: str, /, **parameters: Any) -> None:
    """Execute one write query and eagerly consume its result when supported."""

    _consume_write_result(tx_or_session.run(query, parameters=parameters))
def _bounded_positive_int_config(name: str, default: int, *, maximum: int) -> int:
    """Return a bounded positive integer from config with a safe fallback."""

    raw_value = os.getenv(name)
    if raw_value is None:
        raw_value = get_config_value(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        return max(1, min(int(raw_value), maximum))
    except ValueError:
        return default
def add_repository_to_graph(
    builder: Any,
    repo_path: Path,
    is_dependency: bool,
    *,
    git_remote_for_path_fn: Any,
    repository_metadata_fn: Any,
) -> None:
    """Merge a repository node using the canonical remote-first identity.

    Args:
        builder: ``GraphBuilder`` facade instance.
        repo_path: Repository root to persist.
        is_dependency: Whether the repository is indexed as a dependency.
        git_remote_for_path_fn: Callable resolving the repository remote URL.
        repository_metadata_fn: Callable building canonical repository metadata.
    """
    repo_path_str = str(repo_path.resolve())
    remote_url = git_remote_for_path_fn(repo_path)
    metadata = repository_metadata_fn(
        name=repo_path.name,
        local_path=repo_path_str,
        remote_url=remote_url,
    )

    with builder.driver.session() as session:
        existing = session.run(
            """
            MATCH (r:Repository {path: $repo_path})
            RETURN r.id as id
            LIMIT 1
            """,
            repo_path=repo_path_str,
        ).single()
        if existing is None:
            existing = session.run(
                """
                MATCH (r:Repository {id: $repo_id})
                RETURN r.id as id
                LIMIT 1
                """,
                repo_id=metadata["id"],
            ).single()

        if existing is None:
            _run_write_query(
                session,
                """
                CREATE (r:Repository {path: $repo_path})
                SET r.id = $repo_id,
                    r.name = $name,
                    r.local_path = $local_path,
                    r.remote_url = $remote_url,
                    r.repo_slug = $repo_slug,
                    r.has_remote = $has_remote,
                    r.is_dependency = $is_dependency
                """,
                repo_id=metadata["id"],
                repo_path=repo_path_str,
                local_path=metadata["local_path"],
                name=metadata["name"],
                remote_url=metadata["remote_url"],
                repo_slug=metadata["repo_slug"],
                has_remote=metadata["has_remote"],
                is_dependency=is_dependency,
            )
            return

        _run_write_query(
            session,
            """
            MATCH (r:Repository)
            WHERE r.path = $repo_path OR r.id = $repo_id
            SET r.id = $repo_id,
                r.name = $name,
                r.path = $repo_path,
                r.local_path = $local_path,
                r.remote_url = $remote_url,
                r.repo_slug = $repo_slug,
                r.has_remote = $has_remote,
                r.is_dependency = $is_dependency
            """,
            repo_id=metadata["id"],
            repo_path=repo_path_str,
            local_path=metadata["local_path"],
            name=metadata["name"],
            remote_url=metadata["remote_url"],
            repo_slug=metadata["repo_slug"],
            has_remote=metadata["has_remote"],
            is_dependency=is_dependency,
        )
def _merge_directory_chain(
    tx: Any,
    file_path_obj: Path,
    repo_path_obj: Path,
    file_path_str: str,
) -> None:
    """Write the directory chain and file-containment edge within a transaction.

    Args:
        tx: Open Neo4j transaction.
        file_path_obj: Resolved absolute file path.
        repo_path_obj: Resolved repository root.
        file_path_str: String form of the resolved file path.
    """
    try:
        relative_path_to_file = file_path_obj.relative_to(repo_path_obj)
    except ValueError:
        relative_path_to_file = Path(file_path_obj.name)

    parent_path = str(repo_path_obj)
    parent_label = "Repository"

    for part in relative_path_to_file.parts[:-1]:
        current_path = Path(parent_path) / part
        current_path_str = str(current_path)

        _run_write_query(
            tx,
            f"""
            MATCH (p:{parent_label} {{path: $parent_path}})
            MERGE (d:Directory {{path: $current_path}})
            SET d.name = $part
            MERGE (p)-[:CONTAINS]->(d)
            """,
            parent_path=parent_path,
            current_path=current_path_str,
            part=part,
        )

        parent_path = current_path_str
        parent_label = "Directory"

    _run_write_query(
        tx,
        """
        MATCH (r:Repository {path: $repo_path})
        MATCH (f:File {path: $file_path})
        MERGE (r)-[:REPO_CONTAINS]->(f)
        """,
        repo_path=str(repo_path_obj),
        file_path=file_path_str,
    )

    _run_write_query(
        tx,
        f"""
        MATCH (p:{parent_label} {{path: $parent_path}})
        MATCH (f:File {{path: $file_path}})
        MERGE (p)-[:CONTAINS]->(f)
        """,
        parent_path=parent_path,
        file_path=file_path_str,
    )
def _content_dual_write(
    file_data: dict[str, Any],
    file_name: str,
    repository: dict[str, Any],
    warning_logger_fn: Any,
) -> None:
    """Attempt a Postgres content-store dual-write for one file.

    Args:
        file_data: Parsed file payload.
        file_name: Basename of the file (for log messages).
        repository: Canonical repository metadata dict.
        warning_logger_fn: Warning logger callable.
    """
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
        # Read repo metadata outside the write transaction (auto-commit read).
        try:
            repo_result = session.run(
                """
                MATCH (r:Repository {path: $repo_path})
                RETURN r.id as id,
                       r.name as name,
                       r.path as path,
                       coalesce(r[$local_path_key], r.path) as local_path,
                       r[$remote_url_key] as remote_url,
                       r[$repo_slug_key] as repo_slug,
                       coalesce(r[$has_remote_key], false) as has_remote
                """,
                repo_path=str(repo_path_obj),
                local_path_key="local_path",
                remote_url_key="remote_url",
                repo_slug_key="repo_slug",
                has_remote_key="has_remote",
            ).single()
        except ValueError:
            repo_result = None

        repo_row = record_to_dict(repo_result) if repo_result is not None else None
        repository = repository_metadata_from_row(row=repo_row, repo_path=repo_path_obj)

        try:
            relative_path = file_path_obj.relative_to(repo_path_obj).as_posix()
        except ValueError:
            relative_path = file_name

        # Postgres content dual-write is outside the Neo4j transaction.
        _content_dual_write(file_data, file_name, repository, warning_logger_fn)
        max_entity_value_length = resolve_max_entity_value_length(get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH"))

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

                _merge_directory_chain(tx, file_path_obj, repo_path_obj, file_path_str)

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
) -> None:
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
        return

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
    max_entity_value_length = resolve_max_entity_value_length(get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH"))
    tx_file_limit = _bounded_positive_int_config(
        "PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE",
        5,
        maximum=max(1, len(file_data_list)),
    )

    with builder.driver.session() as session:
        # Single read to get repo metadata for the whole batch.
        try:
            repo_result = session.run(
                """
                MATCH (r:Repository {path: $repo_path})
                RETURN r.id as id,
                       r.name as name,
                       r.path as path,
                       coalesce(r[$local_path_key], r.path) as local_path,
                       r[$remote_url_key] as remote_url,
                       r[$repo_slug_key] as repo_slug,
                       coalesce(r[$has_remote_key], false) as has_remote
                """,
                repo_path=repo_path_str,
                local_path_key="local_path",
                remote_url_key="remote_url",
                repo_slug_key="repo_slug",
                has_remote_key="has_remote",
            ).single()
        except ValueError:
            repo_result = None

        repo_row = record_to_dict(repo_result) if repo_result is not None else None
        repository = repository_metadata_from_row(row=repo_row, repo_path=repo_path_obj)
        total_files = len(file_data_list)
        committed_files = 0

        for start in range(0, total_files, tx_file_limit):
            tx_chunk = file_data_list[start : start + tx_file_limit]
            for file_data in tx_chunk:
                file_name = Path(file_data["path"]).name
                _content_dual_write(file_data, file_name, repository, warning_logger_fn)

            tx, is_explicit = _begin_transaction(session)
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
                        file_path_str = str(Path(file_data["path"]).resolve())
                        file_path_obj = Path(file_path_str)
                        file_name = Path(file_path_str).name
                        is_dependency = file_data.get("is_dependency", False)

                        try:
                            relative_path = file_path_obj.relative_to(repo_path_obj).as_posix()
                        except ValueError:
                            relative_path = file_name

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

                        _merge_directory_chain(tx, file_path_obj, repo_path_obj, file_path_str)

                        file_batches = collect_file_write_data(
                            file_data,
                            file_path_str,
                            max_entity_value_length=max_entity_value_length,
                        )
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
            except Exception:
                if is_explicit:
                    tx.rollback()
                raise

            committed_files += len(tx_chunk)
            if callable(progress_callback) and tx_chunk:
                progress_callback(
                    processed_files=committed_files,
                    total_files=total_files,
                    current_file=str(Path(tx_chunk[-1]["path"]).resolve()),
                    committed=True,
                )
__all__ = [
    "add_file_to_graph",
    "add_repository_to_graph",
    "commit_file_batch_to_graph",
]
