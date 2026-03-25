"""Repository statistics query helpers."""

from __future__ import annotations

from typing import Any

from ...runtime.status_store import get_repository_coverage as get_runtime_repository_coverage
from .common import canonical_repository_ref, resolve_repository
from .coverage_data import coverage_summary_from_row
from .graph_counts import repository_graph_counts


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
        counts = repository_graph_counts(session, repo)
        coverage_summary = coverage_summary_from_row(
            get_runtime_repository_coverage(repo_id=repo_ref["id"])
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
            },
            "coverage": coverage_summary,
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
