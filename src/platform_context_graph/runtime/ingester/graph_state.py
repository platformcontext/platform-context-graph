"""Graph-state helpers for repo-sync self-healing decisions."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from platform_context_graph.core import get_database_manager
from platform_context_graph.utils.debug_log import warning_logger


def graph_missing_repository_paths(repository_paths: Iterable[Path]) -> list[Path]:
    """Return discovered repo checkouts that do not currently exist in the graph."""

    repo_paths = sorted(
        path.resolve()
        for path in repository_paths
        if path.is_dir() and (path / ".git").exists()
    )
    if not repo_paths:
        return []

    try:
        db_manager = get_database_manager()
        with db_manager.get_driver().session() as session:
            rows = session.run(
                """
                UNWIND $repo_paths AS repo_path
                OPTIONAL MATCH (r:Repository {path: repo_path})
                RETURN repo_path, count(r) AS repo_count
                """,
                repo_paths=[str(path) for path in repo_paths],
            ).data()
    except Exception as exc:
        warning_logger(
            "Skipping graph recovery probe for repo sync: "
            f"failed to query repository graph state: {exc}"
        )
        return []

    missing_paths = [
        Path(str(row["repo_path"])).resolve()
        for row in rows
        if int(row.get("repo_count") or 0) == 0
    ]
    return sorted(missing_paths)


__all__ = ["graph_missing_repository_paths"]
