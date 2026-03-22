"""Repository statistics query helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import canonical_repository_ref, resolve_repository


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

        repo_path = str(Path((repo.get("local_path") or repo["path"])).resolve())
        repo_ref = canonical_repository_ref(repo)
        return {
            "success": True,
            "repository": repo_ref,
            "stats": {
                "files": _single_count(
                    session,
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File) RETURN count(f) as c",
                    path=repo_path,
                ),
                "functions": _single_count(
                    session,
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(func:Function) RETURN count(func) as c",
                    path=repo_path,
                ),
                "classes": _single_count(
                    session,
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(cls:Class) RETURN count(cls) as c",
                    path=repo_path,
                ),
                "modules": _single_count(
                    session,
                    "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(f:File)-[:IMPORTS]->(m:Module) RETURN count(DISTINCT m) as c",
                    path=repo_path,
                ),
            },
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

    return session.run(query, **params).single()["c"]
