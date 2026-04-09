"""File graph projection helpers driven by stored facts."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Callable
from typing import Iterable

from platform_context_graph.content.ingest import repository_metadata_from_row
from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.graph.persistence.file_nodes import (
    FILE_NODE_MERGE_QUERY,
)
from platform_context_graph.graph.persistence.file_nodes import (
    build_file_node_write_params,
)
from platform_context_graph.graph.persistence.content_store import content_dual_write
from platform_context_graph.graph.persistence.content_store import (
    content_dual_write_batch,
)
from platform_context_graph.observability import get_observability

from .common import run_write_query
from .repositories import _normalized_fact_type

CollectDirectoryChainRowsFn = Callable[
    ..., tuple[list[dict[str, str]], list[dict[str, str]]]
]
ContentDualWriteFn = Callable[..., None]
ContentDualWriteBatchFn = Callable[..., None]
FlushDirectoryChainRowsFn = Callable[..., None]

_DEFAULT_FILE_BATCH_SIZE = max(
    1,
    int(os.getenv("PCG_RESOLUTION_FILE_BATCH_SIZE", "250")),
)


def collect_directory_chain_rows(
    file_path_obj: Path,
    repo_path_obj: Path,
    file_path_str: str,
    *,
    warning_logger_fn: object | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return directory and containment rows without runtime-side imports."""

    del warning_logger_fn
    relative_path_to_file = file_path_obj.relative_to(repo_path_obj)

    dir_rows: list[dict[str, str]] = []
    parent_path = str(repo_path_obj)
    parent_label = "Repository"
    for part in relative_path_to_file.parts[:-1]:
        current_path = str(Path(parent_path) / part)
        dir_rows.append(
            {
                "parent_path": parent_path,
                "parent_label": parent_label,
                "current_path": current_path,
                "part": part,
            }
        )
        parent_path = current_path
        parent_label = "Directory"

    return dir_rows, [
        {
            "repo_path": str(repo_path_obj),
            "file_path": file_path_str,
            "parent_path": parent_path,
            "parent_label": parent_label,
        },
    ]


def flush_directory_chain_rows(
    tx: object,
    dir_rows: list[dict[str, str]],
    containment_rows: list[dict[str, str]],
) -> None:
    """Write collected directory chains via the local write helper."""

    if dir_rows:
        repository_rows = [
            row for row in dir_rows if row["parent_label"] == "Repository"
        ]
        directory_rows = [row for row in dir_rows if row["parent_label"] == "Directory"]
        if repository_rows:
            run_write_query(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Repository {path: row.parent_path})
                MERGE (d:Directory {path: row.current_path})
                SET d.name = row.part
                MERGE (p)-[:CONTAINS]->(d)
                """,
                rows=repository_rows,
            )
        if directory_rows:
            run_write_query(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Directory {path: row.parent_path})
                MERGE (d:Directory {path: row.current_path})
                SET d.name = row.part
                MERGE (p)-[:CONTAINS]->(d)
                """,
                rows=directory_rows,
            )

    if containment_rows:
        run_write_query(
            tx,
            """
            UNWIND $rows AS row
            MATCH (r:Repository {path: row.repo_path})
            MATCH (f:File {path: row.file_path})
            MERGE (r)-[:REPO_CONTAINS]->(f)
            """,
            rows=containment_rows,
        )
        repository_rows = [
            row for row in containment_rows if row["parent_label"] == "Repository"
        ]
        directory_rows = [
            row for row in containment_rows if row["parent_label"] == "Directory"
        ]
        if repository_rows:
            run_write_query(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Repository {path: row.parent_path})
                MATCH (f:File {path: row.file_path})
                MERGE (p)-[:CONTAINS]->(f)
                """,
                rows=repository_rows,
            )
        if directory_rows:
            run_write_query(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Directory {path: row.parent_path})
                MATCH (f:File {path: row.file_path})
                MERGE (p)-[:CONTAINS]->(f)
                """,
                rows=directory_rows,
            )


def iter_file_facts(fact_records: Iterable[FactRecordRow]) -> list[FactRecordRow]:
    """Return file observation facts in stable insertion order."""

    seen_fact_ids: set[str] = set()
    file_facts: list[FactRecordRow] = []
    for fact_record in fact_records:
        if _normalized_fact_type(fact_record.fact_type) != "FileObserved":
            continue
        if fact_record.fact_id in seen_fact_ids:
            continue
        seen_fact_ids.add(fact_record.fact_id)
        file_facts.append(fact_record)
    return file_facts


def _iter_file_fact_batches(
    file_facts: list[FactRecordRow],
    *,
    batch_size: int,
) -> Iterable[list[FactRecordRow]]:
    """Yield file-fact batches in stable insertion order."""

    for start in range(0, len(file_facts), batch_size):
        yield file_facts[start : start + batch_size]


def project_file_facts(
    tx: object,
    fact_records: Iterable[FactRecordRow],
    *,
    warning_logger_fn: object | None = None,
    content_dual_write_fn: ContentDualWriteFn = content_dual_write,
    content_dual_write_batch_fn: ContentDualWriteBatchFn = content_dual_write_batch,
    collect_directory_chain_rows_fn: CollectDirectoryChainRowsFn = (
        collect_directory_chain_rows
    ),
    flush_directory_chain_rows_fn: FlushDirectoryChainRowsFn = flush_directory_chain_rows,
    file_batch_size: int | None = None,
) -> int:
    """Project file facts into File nodes and repository containment edges."""

    file_facts = iter_file_facts(fact_records)
    if not file_facts:
        return 0

    batch_size = max(1, file_batch_size or _DEFAULT_FILE_BATCH_SIZE)
    first_repo_path = Path(file_facts[0].checkout_path).resolve()
    repository = repository_metadata_from_row(
        row={
            "id": file_facts[0].repository_id,
            "name": first_repo_path.name,
            "path": str(first_repo_path),
            "local_path": str(first_repo_path),
            "has_remote": False,
        },
        repo_path=first_repo_path,
    )

    projected = 0
    observability = get_observability()
    for file_batch in _iter_file_fact_batches(file_facts, batch_size=batch_size):
        batch_file_data: list[dict[str, object]] = []
        dir_rows: list[dict[str, str]] = []
        containment_rows: list[dict[str, str]] = []
        started = time.perf_counter()
        with observability.start_span(
            "pcg.resolution.project_file_batch",
            attributes={
                "pcg.repository_id": repository.get("id"),
                "pcg.file_count": len(file_batch),
            },
        ):
            for fact_record in file_batch:
                if not fact_record.relative_path:
                    continue
                repo_path = Path(fact_record.checkout_path).resolve()
                file_path = repo_path / fact_record.relative_path
                parsed_file_data = fact_record.payload.get("parsed_file_data")
                if isinstance(parsed_file_data, dict):
                    file_data = dict(parsed_file_data)
                    file_data.setdefault("path", str(file_path))
                    file_data.setdefault("repo_path", str(repo_path))
                    file_data["is_dependency"] = bool(
                        fact_record.payload.get("is_dependency", False)
                    )
                    batch_file_data.append(file_data)
                run_write_query(
                    tx,
                    FILE_NODE_MERGE_QUERY,
                    **build_file_node_write_params(
                        file_path=str(file_path),
                        name=file_path.name,
                        relative_path=fact_record.relative_path,
                        language=fact_record.payload.get("language"),
                        is_dependency=bool(
                            fact_record.payload.get("is_dependency", False)
                        ),
                        file_data=(
                            parsed_file_data
                            if isinstance(parsed_file_data, dict)
                            else None
                        ),
                    ),
                )
                repo_dir_rows, repo_containment_rows = collect_directory_chain_rows_fn(
                    file_path,
                    repo_path,
                    str(file_path),
                    warning_logger_fn=warning_logger_fn,
                )
                dir_rows.extend(repo_dir_rows)
                containment_rows.extend(repo_containment_rows)
                projected += 1

            if batch_file_data:
                content_dual_write_batch_fn(
                    batch_file_data,
                    repository,
                    warning_logger_fn,
                )
            flush_directory_chain_rows_fn(tx, dir_rows, containment_rows)
        observability.record_resolution_file_projection_batch(
            component=observability.component,
            file_count=len(file_batch),
            duration_seconds=time.perf_counter() - started,
        )
        observability.record_resolution_directory_flush_rows(
            component=observability.component,
            row_kind="directory",
            row_count=len(dir_rows),
        )
        observability.record_resolution_directory_flush_rows(
            component=observability.component,
            row_kind="containment",
            row_count=len(containment_rows),
        )

    return projected


__all__ = [
    "iter_file_facts",
    "project_file_facts",
]
