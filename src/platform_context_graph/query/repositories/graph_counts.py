"""Graph-backed repository count helpers shared by context, stats, and coverage."""

from __future__ import annotations

from typing import Any

_SCOPE_PREDICATE = (
    "(($repo_id IS NOT NULL AND r.id = $repo_id) "
    "OR ($repo_path IS NOT NULL AND coalesce(r.local_path, r.path) = $repo_path))"
)

__all__ = ["repository_graph_counts", "repository_scope", "repository_scope_predicate"]


def repository_scope(repo: dict[str, Any]) -> dict[str, Any]:
    """Build the repository scope parameters for shared Cypher count queries."""

    return {
        "repo_id": repo.get("id"),
        "repo_path": repo.get("local_path") or repo.get("path"),
    }


def repository_scope_predicate() -> str:
    """Return the shared Cypher predicate for scoping one repository."""

    return _SCOPE_PREDICATE


def repository_graph_counts(session: Any, repo: dict[str, Any]) -> dict[str, int]:
    """Return aligned root/recursive code counts for one repository."""

    row = session.run(
        f"""
        MATCH (r:Repository)
        WHERE {repository_scope_predicate()}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS]->(root_file:File)
            RETURN count(DISTINCT root_file) AS root_file_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS]->(root_directory:Directory)
            RETURN count(DISTINCT root_directory) AS root_directory_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS*]->(file:File)
            RETURN count(DISTINCT file) AS file_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS*]->(:File)-[:CONTAINS]->(fn:Function)
            WHERE NOT EXISTS {{
                MATCH (:Class)-[:CONTAINS]->(fn)
            }}
            RETURN count(DISTINCT fn) AS top_level_function_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS*]->(:Class)-[:CONTAINS]->(fn:Function)
            RETURN count(DISTINCT fn) AS class_method_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS*]->(fn:Function)
            RETURN count(DISTINCT fn) AS total_function_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS*]->(cls:Class)
            RETURN count(DISTINCT cls) AS class_count
        }}
        CALL (r) {{
            OPTIONAL MATCH (r)-[:CONTAINS*]->(:File)-[:IMPORTS]->(module:Module)
            RETURN count(DISTINCT module) AS module_count
        }}
        RETURN root_file_count,
               root_directory_count,
               file_count,
               top_level_function_count,
               class_method_count,
               total_function_count,
               class_count,
               module_count
        """,
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
