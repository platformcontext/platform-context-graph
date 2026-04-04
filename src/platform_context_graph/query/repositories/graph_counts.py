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
        "imports_rel_type": "IMPORTS",
    }


def repository_scope_predicate() -> str:
    """Return the shared Cypher predicate for scoping one repository."""

    return _SCOPE_PREDICATE


def _count_subquery(query: str, alias: str) -> str:
    """Wrap a count query in a repository-scoped subquery."""

    return f"""
        CALL (r) {{
            {query}
            RETURN count(DISTINCT counted) AS {alias}
        }}
    """


def _zero_subquery(alias: str) -> str:
    """Return a zero-valued subquery for absent relationship types."""

    return f"""
        CALL (r) {{
            RETURN 0 AS {alias}
        }}
    """


def _build_graph_counts_query(relationship_types: set[str]) -> str:
    """Build the repository count query for the current graph schema."""

    has_contains = "CONTAINS" in relationship_types
    has_repo_contains = "REPO_CONTAINS" in relationship_types
    has_imports = "IMPORTS" in relationship_types

    subqueries = [
        _count_subquery(
            "OPTIONAL MATCH (r)-[:CONTAINS]->(counted:File)",
            "root_file_count",
        )
        if has_contains
        else _zero_subquery("root_file_count"),
        _count_subquery(
            "OPTIONAL MATCH (r)-[:CONTAINS]->(counted:Directory)",
            "root_directory_count",
        )
        if has_contains
        else _zero_subquery("root_directory_count"),
        _count_subquery(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(counted:File)",
            "file_count",
        )
        if has_repo_contains
        else _zero_subquery("file_count"),
        _count_subquery(
            """
            OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(counted:Function)
            WHERE NOT EXISTS {
                MATCH (:Class)-[:CONTAINS]->(counted)
            }
            """.strip(),
            "top_level_function_count",
        )
        if has_repo_contains and has_contains
        else _zero_subquery("top_level_function_count"),
        _count_subquery(
            """
            OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(:Class)-[:CONTAINS]->(counted:Function)
            """.strip(),
            "class_method_count",
        )
        if has_repo_contains and has_contains
        else _zero_subquery("class_method_count"),
        _count_subquery(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS*]->(counted:Function)",
            "total_function_count",
        )
        if has_repo_contains and has_contains
        else _zero_subquery("total_function_count"),
        _count_subquery(
            "OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS*]->(counted:Class)",
            "class_count",
        )
        if has_repo_contains and has_contains
        else _zero_subquery("class_count"),
        _count_subquery(
            """
            OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[rel]->(counted:Module)
            WHERE type(rel) = $imports_rel_type
            """.strip(),
            "module_count",
        )
        if has_repo_contains and has_imports
        else _zero_subquery("module_count"),
    ]
    return f"""
        MATCH (r:Repository)
        WHERE {repository_scope_predicate()}
        {' '.join(subqueries)}
        RETURN root_file_count,
               root_directory_count,
               file_count,
               top_level_function_count,
               class_method_count,
               total_function_count,
               class_count,
               module_count
    """


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
