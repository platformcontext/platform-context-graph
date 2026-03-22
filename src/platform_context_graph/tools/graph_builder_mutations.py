"""Mutation helpers for file and repository graph updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def delete_file_from_graph(builder: Any, path: str, *, info_logger_fn: Any) -> None:
    """Delete a file node and any contained graph elements.

    Args:
        builder: ``GraphBuilder`` facade instance.
        path: File path to remove from the graph.
        info_logger_fn: Info logger callable.
    """
    file_path_str = str(Path(path).resolve())
    with builder.driver.session() as session:
        parents_res = session.run(
            """
            MATCH (f:File {path: $file_path})<-[:CONTAINS*]-(d:Directory)
            RETURN d.path as path ORDER BY d.path DESC
        """,
            file_path=file_path_str,
        )
        parent_paths = [record["path"] for record in parents_res]

        session.run(
            """
            MATCH (f:File {path: $file_path})
            OPTIONAL MATCH (f)-[:CONTAINS]->(element)
            DETACH DELETE f, element
            """,
            file_path=file_path_str,
        )
        info_logger_fn(f"Deleted file and its elements from graph: {file_path_str}")

        for dir_path in parent_paths:
            session.run(
                """
                MATCH (d:Directory {path: $dir_path})
                WHERE NOT (d)-[:CONTAINS]->()
                DETACH DELETE d
            """,
                dir_path=dir_path,
            )


def delete_repository_from_graph(
    builder: Any,
    repo_path: str,
    *,
    info_logger_fn: Any,
    warning_logger_fn: Any,
) -> bool:
    """Delete a repository subtree from the graph.

    Args:
        builder: ``GraphBuilder`` facade instance.
        repo_path: Repository path to delete.
        info_logger_fn: Info logger callable.
        warning_logger_fn: Warning logger callable.

    Returns:
        ``True`` if the repository existed and was deleted, otherwise ``False``.
    """
    repo_path_str = str(Path(repo_path).resolve())
    with builder.driver.session() as session:
        result = session.run(
            "MATCH (r:Repository {path: $repo_path}) RETURN count(r) as cnt",
            repo_path=repo_path_str,
        ).single()
        if not result or result["cnt"] == 0:
            warning_logger_fn(
                f"Attempted to delete non-existent repository: {repo_path_str}"
            )
            return False

        session.run(
            """MATCH (r:Repository {path: $repo_path})
                      OPTIONAL MATCH (r)-[:CONTAINS*]->(e)
                      DETACH DELETE r, e""",
            repo_path=repo_path_str,
        )
        info_logger_fn(
            f"Deleted repository and its contents from graph: {repo_path_str}"
        )
        return True


def update_file_in_graph(
    builder: Any,
    path: Path,
    repo_path: Path,
    imports_map: dict[str, Any],
    *,
    error_logger_fn: Any,
) -> dict[str, Any] | None:
    """Replace graph state for one file with freshly parsed contents.

    Args:
        builder: ``GraphBuilder`` facade instance.
        path: File path to refresh.
        repo_path: Repository root containing the file.
        imports_map: Import resolution map used for relationship creation.
        error_logger_fn: Error logger callable.

    Returns:
        Parsed file data, a deletion marker, or ``None`` when parsing failed.
    """
    file_path_str = str(path.resolve())
    repo_name = repo_path.name

    builder.delete_file_from_graph(file_path_str)

    if path.exists():
        file_data = builder.parse_file(repo_path, path)
        if "error" not in file_data:
            builder.add_file_to_graph(file_data, repo_name, imports_map)
            return file_data

        error_logger_fn(
            f"Skipping graph add for {file_path_str} due to parsing error: {file_data['error']}"
        )
        return None

    return {"deleted": True, "path": file_path_str}


__all__ = [
    "delete_file_from_graph",
    "delete_repository_from_graph",
    "update_file_in_graph",
]
