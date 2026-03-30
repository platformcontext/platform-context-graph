"""Directory-chain helpers shared by graph builder persistence paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def merge_directory_chain(
    tx: Any,
    file_path_obj: Path,
    repo_path_obj: Path,
    file_path_str: str,
    *,
    relative_path_with_fallback_fn: Any,
    run_write_query_fn: Any,
    warning_logger_fn: Any | None = None,
) -> None:
    """Write the directory chain and file-containment edge within a transaction."""
    relative_path_to_file = relative_path_with_fallback_fn(
        file_path_obj,
        repo_path_obj,
        warning_logger_fn=warning_logger_fn,
        operation="directory chain merge",
    )

    parent_path = str(repo_path_obj)
    parent_label = "Repository"
    for part in relative_path_to_file.parts[:-1]:
        current_path_str = str(Path(parent_path) / part)
        try:
            run_write_query_fn(
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
        except Exception as exc:
            raise RuntimeError(
                (
                    f"Failed to merge directory chain for {file_path_str} "
                    f"at directory {current_path_str}"
                )
            ) from exc
        parent_path = current_path_str
        parent_label = "Directory"

    run_write_query_fn(
        tx,
        """
        MATCH (r:Repository {path: $repo_path})
        MATCH (f:File {path: $file_path})
        MERGE (r)-[:REPO_CONTAINS]->(f)
        """,
        repo_path=str(repo_path_obj),
        file_path=file_path_str,
    )
    run_write_query_fn(
        tx,
        f"""
        MATCH (p:{parent_label} {{path: $parent_path}})
        MATCH (f:File {{path: $file_path}})
        MERGE (p)-[:CONTAINS]->(f)
        """,
        parent_path=parent_path,
        file_path=file_path_str,
    )


def collect_directory_chain_rows(
    file_path_obj: Path,
    repo_path_obj: Path,
    file_path_str: str,
    *,
    relative_path_with_fallback_fn: Any,
    warning_logger_fn: Any | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return directory and containment rows without executing queries."""
    relative_path_to_file = relative_path_with_fallback_fn(
        file_path_obj,
        repo_path_obj,
        warning_logger_fn=warning_logger_fn,
        operation="directory chain collect",
    )

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
    tx: Any,
    dir_rows: list[dict[str, str]],
    containment_rows: list[dict[str, str]],
    *,
    run_write_query_fn: Any,
) -> None:
    """Write collected directory chains via UNWIND queries."""
    if dir_rows:
        repo_parent_rows = [row for row in dir_rows if row["parent_label"] == "Repository"]
        dir_parent_rows = [row for row in dir_rows if row["parent_label"] == "Directory"]

        if repo_parent_rows:
            run_write_query_fn(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Repository {path: row.parent_path})
                MERGE (d:Directory {path: row.current_path})
                SET d.name = row.part
                MERGE (p)-[:CONTAINS]->(d)
                """,
                rows=repo_parent_rows,
            )
        if dir_parent_rows:
            run_write_query_fn(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Directory {path: row.parent_path})
                MERGE (d:Directory {path: row.current_path})
                SET d.name = row.part
                MERGE (p)-[:CONTAINS]->(d)
                """,
                rows=dir_parent_rows,
            )

    if containment_rows:
        run_write_query_fn(
            tx,
            """
            UNWIND $rows AS row
            MATCH (r:Repository {path: row.repo_path})
            MATCH (f:File {path: row.file_path})
            MERGE (r)-[:REPO_CONTAINS]->(f)
            """,
            rows=containment_rows,
        )

        repo_file_rows = [row for row in containment_rows if row["parent_label"] == "Repository"]
        dir_file_rows = [row for row in containment_rows if row["parent_label"] == "Directory"]

        if repo_file_rows:
            run_write_query_fn(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Repository {path: row.parent_path})
                MATCH (f:File {path: row.file_path})
                MERGE (p)-[:CONTAINS]->(f)
                """,
                rows=repo_file_rows,
            )
        if dir_file_rows:
            run_write_query_fn(
                tx,
                """
                UNWIND $rows AS row
                MATCH (p:Directory {path: row.parent_path})
                MATCH (f:File {path: row.file_path})
                MERGE (p)-[:CONTAINS]->(f)
                """,
                rows=dir_file_rows,
            )
