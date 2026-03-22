"""Repository listing queries."""

from __future__ import annotations

from typing import Any

from .common import (
    get_db_manager,
    repository_metadata_from_row,
    repository_projection,
)


def list_repositories_rows(database: Any) -> list[dict[str, Any]]:
    """Return raw repository listing rows enriched for API responses.

    Args:
        database: Query-layer database dependency.

    Returns:
        Repository listing rows in the public response shape.
    """

    driver = get_db_manager(database).get_driver()
    with driver.session() as session:
        repos = session.run(
            f"""
                MATCH (r:Repository)
                RETURN {repository_projection()},
                       coalesce(r.is_dependency, false) as is_dependency
                ORDER BY r.name
                """
        ).data()

    repositories: list[dict[str, Any]] = []
    for repo in repos:
        local_path = repo.get("local_path") or repo.get("path")
        if not local_path:
            continue
        repositories.append(
            {
                **repository_metadata_from_row(repo),
                "is_dependency": bool(repo.get("is_dependency", False)),
            }
        )
    return repositories
