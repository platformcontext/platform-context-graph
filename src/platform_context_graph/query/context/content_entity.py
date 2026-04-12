"""Context helpers for content-entity identifiers."""

from __future__ import annotations

from typing import Any

from ...content.state import get_content_service
from ..data_lineage_evidence import summarize_lineage_edges
from ..impact.database import db_fetch_edges
from ..repositories import _repository_projection
from .support import canonical_ref, record_to_dict


def _lookup_repository_ref(database: Any, repo_id: str) -> dict[str, Any] | None:
    """Return a canonical repository ref for a content entity when available."""
    db_manager = (
        database
        if callable(getattr(database, "get_driver", None))
        else getattr(database, "db_manager", database)
    )
    if not callable(getattr(db_manager, "get_driver", None)):
        return canonical_ref(
            {
                "id": repo_id,
                "type": "repository",
                "name": repo_id.split(":", 1)[-1],
            }
        )

    with db_manager.get_driver().session() as session:
        row = session.run(
            f"""
            MATCH (r:Repository)
            WHERE r.id = $repo_id
            RETURN {_repository_projection()}
            LIMIT 1
            """,
            repo_id=repo_id,
            local_path_key="local_path",
            remote_url_key="remote_url",
            repo_slug_key="repo_slug",
            has_remote_key="has_remote",
        ).single()

    repo = record_to_dict(row)
    if not repo:
        return canonical_ref(
            {
                "id": repo_id,
                "type": "repository",
                "name": repo_id.split(":", 1)[-1],
            }
        )
    return canonical_ref(
        {
            "id": repo["id"],
            "type": "repository",
            "name": repo["name"],
            "path": repo.get("path"),
            "local_path": repo.get("local_path"),
            "repo_slug": repo.get("repo_slug"),
            "remote_url": repo.get("remote_url"),
            "has_remote": repo.get("has_remote"),
        }
    )


def content_entity_context(database: Any, *, entity_id: str) -> dict[str, Any]:
    """Build a generic entity-context payload for a content-bearing entity."""
    result = get_content_service(database).get_entity_content(entity_id=entity_id)
    if isinstance(result, dict) and isinstance(result.get("error"), str):
        return result

    repo_id = result.get("repo_id")
    repositories = (
        [_lookup_repository_ref(database, repo_id)] if isinstance(repo_id, str) else []
    )
    response = {
        "entity": canonical_ref(
            {
                "id": entity_id,
                "type": "content_entity",
                "name": result.get("entity_name") or entity_id,
            }
        ),
        "related": [],
        "repositories": [repo for repo in repositories if repo is not None],
        "relative_path": result.get("relative_path"),
        "entity_type": result.get("entity_type"),
        "entity_name": result.get("entity_name"),
        "start_line": result.get("start_line"),
        "end_line": result.get("end_line"),
        "language": result.get("language"),
        "source_backend": result.get("source_backend"),
    }
    lineage_evidence = summarize_lineage_edges(db_fetch_edges(database, entity_id))
    if lineage_evidence is not None:
        response["lineage_evidence"] = lineage_evidence
    return response


__all__ = ["content_entity_context"]
