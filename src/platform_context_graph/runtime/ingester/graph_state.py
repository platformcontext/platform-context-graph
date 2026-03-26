"""Graph-state helpers for repo-sync self-healing decisions."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from platform_context_graph.core import get_database_manager
from platform_context_graph.repository_identity import (
    git_remote_for_path,
    repository_metadata,
)
from platform_context_graph.utils.debug_log import warning_logger


def graph_recovery_repository_paths(repository_paths: Iterable[Path]) -> list[Path]:
    """Return discovered repos whose graph state is missing or drifted."""

    repo_paths = sorted(
        path.resolve()
        for path in repository_paths
        if path.is_dir() and (path / ".git").exists()
    )
    if not repo_paths:
        return []

    repo_probes = []
    for path in repo_paths:
        metadata = repository_metadata(
            name=path.name,
            local_path=path,
            remote_url=git_remote_for_path(path),
        )
        repo_probes.append(
            {
                "repo_path": str(path),
                "repo_id": metadata["id"],
                **metadata,
            }
        )

    try:
        db_manager = get_database_manager()
        with db_manager.get_driver().session() as session:
            rows = session.run(
                """
                UNWIND $repo_probes AS probe
                OPTIONAL MATCH (r:Repository {id: probe.repo_id})
                WITH probe, r, coalesce(r[$local_path_key], r.path) AS graph_path
                RETURN probe.repo_path AS repo_path,
                       probe.repo_id AS repo_id,
                       probe.remote_url AS remote_url,
                       probe.repo_slug AS repo_slug,
                       graph_path AS graph_path,
                       EXISTS {
                           MATCH (r)-[:CONTAINS*]->(f:File)
                           WHERE f.path IS NOT NULL
                             AND NOT f.path STARTS WITH probe.repo_path + "/"
                       } AS has_foreign_files,
                       CASE
                           WHEN r IS NULL THEN true
                           WHEN graph_path IS NULL THEN true
                           WHEN graph_path <> probe.repo_path THEN true
                           WHEN EXISTS {
                               MATCH (r)-[:CONTAINS*]->(f:File)
                               WHERE f.path IS NOT NULL
                                 AND NOT f.path STARTS WITH probe.repo_path + "/"
                           } THEN true
                           ELSE false
                       END AS needs_recovery
                """,
                repo_probes=repo_probes,
                local_path_key="local_path",
            ).data()
    except Exception as exc:
        warning_logger(
            "Skipping graph recovery probe for repo sync: "
            f"failed to query repository graph state: {exc}"
        )
        return []

    recovery_paths = [
        Path(str(row["repo_path"])).resolve()
        for row in rows
        if bool(row.get("needs_recovery"))
    ]
    return sorted(recovery_paths)


def graph_missing_repository_paths(repository_paths: Iterable[Path]) -> list[Path]:
    """Backwards-compatible alias for the repo graph recovery probe."""

    return graph_recovery_repository_paths(repository_paths)


__all__ = [
    "graph_missing_repository_paths",
    "graph_recovery_repository_paths",
]
