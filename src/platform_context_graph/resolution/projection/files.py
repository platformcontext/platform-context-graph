"""File graph projection helpers driven by stored facts."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .common import run_write_query
from .repositories import _normalized_fact_type

CollectDirectoryChainRowsFn = Callable[
    ..., tuple[list[dict[str, str]], list[dict[str, str]]]
]
FlushDirectoryChainRowsFn = Callable[..., None]


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


def project_file_facts(
    tx: object,
    fact_records: Iterable[FactRecordRow],
    *,
    warning_logger_fn: object | None = None,
    collect_directory_chain_rows_fn: CollectDirectoryChainRowsFn = (
        collect_directory_chain_rows
    ),
    flush_directory_chain_rows_fn: FlushDirectoryChainRowsFn = flush_directory_chain_rows,
) -> int:
    """Project file facts into File nodes and repository containment edges."""

    dir_rows: list[dict[str, str]] = []
    containment_rows: list[dict[str, str]] = []
    projected = 0

    for fact_record in iter_file_facts(fact_records):
        if not fact_record.relative_path:
            continue
        repo_path = Path(fact_record.checkout_path).resolve()
        file_path = repo_path / fact_record.relative_path
        run_write_query(
            tx,
            """
            MERGE (f:File {path: $file_path})
            SET f.name = $name,
                f.relative_path = $relative_path,
                f.lang = $language,
                f.is_dependency = $is_dependency
            """,
            file_path=str(file_path),
            name=file_path.name,
            relative_path=fact_record.relative_path,
            language=fact_record.payload.get("language"),
            is_dependency=bool(fact_record.payload.get("is_dependency", False)),
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

    flush_directory_chain_rows_fn(tx, dir_rows, containment_rows)
    return projected


__all__ = [
    "iter_file_facts",
    "project_file_facts",
]
