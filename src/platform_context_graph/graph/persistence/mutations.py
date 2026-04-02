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


def _repository_lookup_values(repo_identifier: str) -> tuple[str, ...]:
    """Return lookup values for a canonical repository id or checkout path."""

    candidate = repo_identifier.strip()
    if not candidate:
        return ()
    if candidate.startswith("repository:"):
        return (candidate,)
    resolved_path = str(Path(candidate).resolve())
    if resolved_path == candidate:
        return (candidate,)
    return (resolved_path, candidate)


def delete_repository_from_graph(
    builder: Any,
    repo_identifier: str,
    *,
    info_logger_fn: Any,
    debug_logger_fn: Any | None = None,
    warning_logger_fn: Any,
) -> bool:
    """Delete a repository subtree from the graph.

    Args:
        builder: ``GraphBuilder`` facade instance.
        repo_identifier: Canonical repository id or repository path.
        info_logger_fn: Info logger callable.
        debug_logger_fn: Debug logger callable for expected no-op deletes.
        warning_logger_fn: Warning logger callable.

    Returns:
        ``True`` if the repository existed and was deleted, otherwise ``False``.
    """

    lookup_values = _repository_lookup_values(str(repo_identifier))
    if not lookup_values:
        warning_logger_fn("Attempted to delete repository with empty identifier")
        return False
    display_identifier = (
        lookup_values[0]
        if lookup_values and lookup_values[0].startswith("repository:")
        else str(Path(repo_identifier).resolve())
    )
    with builder.driver.session() as session:
        result = session.run(
            """
            MATCH (r:Repository)
            WHERE r.id IN $lookup_values
               OR r.path IN $lookup_values
               OR r[$local_path_key] IN $lookup_values
            RETURN count(r) as cnt
            """,
            lookup_values=lookup_values,
            local_path_key="local_path",
        ).single()
        if not result or result["cnt"] == 0:
            if debug_logger_fn is not None:
                debug_logger_fn(
                    f"Repository already absent from graph; nothing to delete: "
                    f"{display_identifier}"
                )
            return False

        session.run(
            """
            MATCH (r:Repository)
            WHERE r.id IN $lookup_values
               OR r.path IN $lookup_values
               OR r[$local_path_key] IN $lookup_values
            OPTIONAL MATCH (r)-[:CONTAINS*]->(e)
            DETACH DELETE r, e
            """,
            lookup_values=lookup_values,
            local_path_key="local_path",
        )
        info_logger_fn(
            f"Deleted repository and its contents from graph: {display_identifier}"
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
