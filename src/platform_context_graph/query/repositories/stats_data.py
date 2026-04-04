"""Repository statistics query helpers."""

from __future__ import annotations

from typing import Any

from .common import (
    canonical_repository_ref,
    graph_relationship_types,
    resolve_repository,
)
from .graph_counts import repository_graph_counts
from .relationship_summary import build_relationship_summary


def build_repository_stats(session: Any, repo_id: str | None) -> dict[str, Any]:
    """Build repository statistics for one repository or the whole graph.

    Args:
        session: Database session used for statistics queries.
        repo_id: Optional repository identifier to scope the stats.

    Returns:
        Repository statistics payload.
    """

    if repo_id:
        repo = resolve_repository(session, repo_id)
        if not repo:
            return {"success": False, "error": f"Repository not found: {repo_id}"}

        repo_ref = canonical_repository_ref(repo)
        relationship_types = graph_relationship_types(session)
        counts = repository_graph_counts(
            session,
            repo,
            relationship_types=relationship_types,
        )
        relationship_summary = build_relationship_summary(
            session,
            repo_ref,
            relationship_types=relationship_types,
        )
        return {
            "success": True,
            "repository": repo_ref,
            "stats": {
                "files": counts["file_count"],
                "root_files": counts["root_file_count"],
                "root_directories": counts["root_directory_count"],
                "functions": counts["total_function_count"],
                "top_level_functions": counts["top_level_function_count"],
                "class_methods": counts["class_method_count"],
                "classes": counts["class_count"],
                "modules": counts["module_count"],
                "platform_count": relationship_summary["summary"]["platform_count"],
                "deployment_source_count": relationship_summary["summary"][
                    "deployment_source_count"
                ],
                "environment_count": relationship_summary["summary"][
                    "environment_count"
                ],
                "limitations": relationship_summary["limitations"],
            },
            "coverage": relationship_summary["coverage"],
        }

    repo_count = _single_count(session, "MATCH (r:Repository) RETURN count(r) as c")
    if repo_count <= 0:
        return {"success": True, "stats": {}, "message": "No data indexed yet"}

    return {
        "success": True,
        "stats": {
            "repositories": repo_count,
            "files": _single_count(session, "MATCH (f:File) RETURN count(f) as c"),
            "functions": _single_count(
                session, "MATCH (func:Function) RETURN count(func) as c"
            ),
            "classes": _single_count(
                session, "MATCH (cls:Class) RETURN count(cls) as c"
            ),
            "modules": _single_count(session, "MATCH (m:Module) RETURN count(m) as c"),
        },
    }


def _single_count(session: Any, query: str, **params: Any) -> int:
    """Execute a count query and extract the ``c`` column.

    Args:
        session: Database session used for the query.
        query: Cypher count query that returns ``c``.
        **params: Query parameters.

    Returns:
        Integer count value.
    """

    return session.run(query, params).single()["c"]
