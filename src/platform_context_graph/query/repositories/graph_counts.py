"""Graph-backed repository count helpers shared by context, stats, and coverage."""

from __future__ import annotations

from typing import Any

from .common import graph_relationship_types

_SCOPE_PREDICATE = (
    "(($repo_id IS NOT NULL AND r.id = $repo_id) "
    "OR ($repo_path IS NOT NULL AND coalesce(r[$local_path_key], r.path) = $repo_path))"
)

__all__ = ["repository_graph_counts", "repository_scope", "repository_scope_predicate"]


def repository_scope(repo: dict[str, Any]) -> dict[str, Any]:
    """Build the repository scope parameters for shared Cypher count queries."""

    return {
        "repo_id": repo.get("id"),
        "repo_path": repo.get("local_path") or repo.get("path"),
        "local_path_key": "local_path",
    }


def repository_scope_predicate() -> str:
    """Return the shared Cypher predicate for scoping one repository."""

    return _SCOPE_PREDICATE


def _append_count_stage(
    lines: list[str],
    carried_aliases: list[str],
    *,
    match_query: str | None,
    alias: str,
    count_expression: str = "count(DISTINCT counted)",
) -> None:
    """Append one backend-compatible count stage to the shared query."""

    with_clause = ", ".join(["r", *carried_aliases])
    if match_query is None:
        lines.append(f"WITH {with_clause}, 0 AS {alias}")
    else:
        lines.append(match_query)
        lines.append(f"WITH {with_clause}, {count_expression} AS {alias}")
    carried_aliases.append(alias)


def _build_graph_counts_query(relationship_types: set[str]) -> str:
    """Build the repository count query for the current graph schema."""

    has_contains = "CONTAINS" in relationship_types
    has_repo_contains = "REPO_CONTAINS" in relationship_types
    has_imports = "IMPORTS" in relationship_types

    lines = [
        "MATCH (r:Repository)",
        f"WHERE {repository_scope_predicate()}",
    ]
    aliases: list[str] = []
    _append_count_stage(
        lines,
        aliases,
        match_query=(
            "OPTIONAL MATCH (r)-[:CONTAINS]->(counted:File)" if has_contains else None
        ),
        alias="root_file_count",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=(
            "OPTIONAL MATCH (r)-[:CONTAINS]->(counted:Directory)"
            if has_contains
            else None
        ),
        alias="root_directory_count",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(counted:File)"
            if has_repo_contains
            else None
        ),
        alias="file_count",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=("""
            OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(counted:Function)
            OPTIONAL MATCH (class_owner:Class)-[:CONTAINS]->(counted)
            """.strip() if has_repo_contains and has_contains else None),
        alias="top_level_function_count",
        count_expression="count(DISTINCT CASE WHEN class_owner IS NULL THEN counted END)",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=("""
            OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(:Class)-[:CONTAINS]->(counted:Function)
            """.strip() if has_repo_contains and has_contains else None),
        alias="class_method_count",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS*]->(counted:Function)"
            if has_repo_contains and has_contains
            else None
        ),
        alias="total_function_count",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS*]->(counted:Class)"
            if has_repo_contains and has_contains
            else None
        ),
        alias="class_count",
    )
    _append_count_stage(
        lines,
        aliases,
        match_query=(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:IMPORTS]->(counted:Module)"
            if has_repo_contains and has_imports
            else None
        ),
        alias="module_count",
    )
    lines.append(
        "RETURN root_file_count,\n"
        "       root_directory_count,\n"
        "       file_count,\n"
        "       top_level_function_count,\n"
        "       class_method_count,\n"
        "       total_function_count,\n"
        "       class_count,\n"
        "       module_count"
    )
    return "\n".join(lines)


def repository_graph_counts(
    session: Any,
    repo: dict[str, Any],
    relationship_types: set[str] | None = None,
) -> dict[str, int]:
    """Return aligned root/recursive code counts for one repository.

    Callers that already fetched graph relationship types may pass them in to
    avoid a second metadata round-trip.
    """

    if relationship_types is None:
        relationship_types = graph_relationship_types(session)
    row = session.run(
        _build_graph_counts_query(relationship_types),
        parameters=repository_scope(repo),
    ).single()
    if row is None:
        return {
            "root_file_count": 0,
            "root_directory_count": 0,
            "file_count": 0,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "module_count": 0,
        }
    return {
        "root_file_count": int(row.get("root_file_count") or 0),
        "root_directory_count": int(row.get("root_directory_count") or 0),
        "file_count": int(row.get("file_count") or 0),
        "top_level_function_count": int(row.get("top_level_function_count") or 0),
        "class_method_count": int(row.get("class_method_count") or 0),
        "total_function_count": int(row.get("total_function_count") or 0),
        "class_count": int(row.get("class_count") or 0),
        "module_count": int(row.get("module_count") or 0),
    }
