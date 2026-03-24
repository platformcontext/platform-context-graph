"""Persistence helpers for repository and file graph updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cli.config_manager import get_config_value
from ..core.records import record_to_dict
from ..content.ingest import (
    prepare_content_entries,
    repository_metadata_from_row,
)
from ..content.state import get_postgres_content_provider
from .graph_builder_persistence_batch import (
    _LARGE_LABEL_SUMMARY_THRESHOLD,
    collect_file_write_data,
    empty_accumulator,
    flush_write_batches,
    merge_batches,
    summarize_entity_source_files,
)
from .graph_builder_persistence_unwind import resolve_max_entity_value_length


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
            session.run(
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

        session.run(
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

        tx.run(
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

    tx.run(
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
    try:
        file_entry, entity_entries = prepare_content_entries(
            file_data=file_data,
            repository=repository,
        )
        if file_entry is not None:
            content_provider.upsert_file(file_entry)
        if entity_entries:
            content_provider.upsert_entities(entity_entries)
    except Exception as exc:
        warning_logger_fn(f"Content store dual-write failed for {file_name}: {exc}")


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
    debug_log_fn(
        f"Executing add_file_to_graph for {file_data.get('path', 'unknown')} - Calls found: {calls_count}"
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
                       coalesce(r.local_path, r.path) as local_path,
                       r.remote_url as remote_url,
                       r.repo_slug as repo_slug,
                       coalesce(r.has_remote, false) as has_remote
                """,
                repo_path=str(repo_path_obj),
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
        max_entity_value_length = resolve_max_entity_value_length(
            get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
        )

        # All Neo4j writes go inside a single explicit transaction when
        # the backend supports it; otherwise fall back to auto-commit.
        tx, is_explicit = _begin_transaction(session)
        try:
            tx.run(
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
    debug_log_fn: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
) -> None:
    """Persist a batch of parsed files in a single Neo4j transaction.

    Opens one session, reads repository metadata once, then writes all files,
    directory chains, entities, imports, and edges via UNWIND queries in one
    explicit transaction.  Postgres content writes are handled per-file outside
    the Neo4j transaction.

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

    debug_log_fn(
        f"commit_file_batch_to_graph: {len(file_data_list)} files for {repo_path_str}"
    )
    max_entity_value_length = resolve_max_entity_value_length(
        get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
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
                       coalesce(r.local_path, r.path) as local_path,
                       r.remote_url as remote_url,
                       r.repo_slug as repo_slug,
                       coalesce(r.has_remote, false) as has_remote
                """,
                repo_path=repo_path_str,
            ).single()
        except ValueError:
            repo_result = None

        repo_row = record_to_dict(repo_result) if repo_result is not None else None
        repository = repository_metadata_from_row(row=repo_row, repo_path=repo_path_obj)

        # Postgres dual-writes are per-file and happen before the Neo4j tx.
        for file_data in file_data_list:
            file_name = Path(file_data["path"]).name
            _content_dual_write(file_data, file_name, repository, warning_logger_fn)

        # One explicit Neo4j transaction for the entire batch when the
        # backend supports it; otherwise fall back to auto-commit.
        tx, is_explicit = _begin_transaction(session)
        try:
            accumulator = empty_accumulator()

            for file_data in file_data_list:
                file_path_str = str(Path(file_data["path"]).resolve())
                file_path_obj = Path(file_path_str)
                file_name = Path(file_path_str).name
                is_dependency = file_data.get("is_dependency", False)

                try:
                    relative_path = file_path_obj.relative_to(repo_path_obj).as_posix()
                except ValueError:
                    relative_path = file_name

                tx.run(
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

            entity_counts = {
                label: len(rows)
                for label, rows in sorted(accumulator["entities_by_label"].items())
                if rows
            }
            if entity_counts:
                entity_summary = ", ".join(
                    f"{label}={count}" for label, count in entity_counts.items()
                )
                info_logger_fn(
                    f"Prepared graph entity batches for {repo_path_str}: {entity_summary}"
                )
                for label, rows in sorted(accumulator["entities_by_label"].items()):
                    if len(rows) < _LARGE_LABEL_SUMMARY_THRESHOLD:
                        continue
                    source_summary = summarize_entity_source_files(
                        rows,
                        repo_root=repo_path_str,
                    )
                    top_files = ", ".join(
                        f"{path}({count})"
                        for path, count in source_summary["top_files"]
                    )
                    if not top_files:
                        continue
                    info_logger_fn(
                        f"Prepared graph entity batch detail for {repo_path_str}: "
                        f"label={label} files={source_summary['file_count']} "
                        f"top_files={top_files}"
                    )
            flush_write_batches(tx, accumulator, info_logger_fn=info_logger_fn)
            if is_explicit:
                tx.commit()
        except Exception:
            if is_explicit:
                tx.rollback()
            raise


__all__ = [
    "add_file_to_graph",
    "add_repository_to_graph",
    "commit_file_batch_to_graph",
]
