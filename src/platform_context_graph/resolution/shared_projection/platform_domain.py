"""Helpers for platform-domain shared projection cutover."""

from __future__ import annotations

from typing import Any


def existing_infrastructure_platform_rows(
    session: Any,
    *,
    repo_ids: list[str],
    evidence_source: str,
) -> list[dict[str, str]]:
    """Return existing infrastructure platform edges for targeted repositories."""

    if not repo_ids:
        return []
    return session.run(
        """
        MATCH (repo:Repository)-[rel:PROVISIONS_PLATFORM]->(p:Platform)
        WHERE repo.id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        RETURN repo.id as repo_id,
               p.id as existing_platform_id
        ORDER BY repo.id, p.id
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    ).data()


def build_platform_infra_intent_rows(
    *,
    descriptor_rows: list[dict[str, object]],
    existing_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Return authoritative platform-domain upsert and retract intent rows."""

    desired_pairs = {
        (
            str(row.get("repo_id") or ""),
            str(row.get("platform_id") or ""),
        )
        for row in descriptor_rows
    }
    intent_rows = [dict(row, action="upsert") for row in descriptor_rows]
    for row in existing_rows:
        pair = (
            str(row.get("repo_id") or ""),
            str(row.get("existing_platform_id") or ""),
        )
        if not pair[0] or not pair[1] or pair in desired_pairs:
            continue
        intent_rows.append(
            {
                "repo_id": pair[0],
                "platform_id": pair[1],
                "action": "retract",
            }
        )
    return intent_rows


def shared_platform_projection_metrics(
    *,
    intent_rows: list[dict[str, object]],
    projection_context_by_repo_id: dict[str, dict[str, str]] | None,
) -> dict[str, object]:
    """Return completion-fencing metadata for authoritative platform cutover."""

    touched_repositories = {
        str(row.get("repo_id") or "") for row in intent_rows if row.get("repo_id")
    }
    if not touched_repositories or not projection_context_by_repo_id:
        return {}
    generation_ids = {
        projection_context_by_repo_id[repo_id]["generation_id"]
        for repo_id in touched_repositories
        if repo_id in projection_context_by_repo_id
    }
    return {
        "authoritative_domains": ["platform_infra"],
        "accepted_generation_id": (
            next(iter(generation_ids)) if len(generation_ids) == 1 else None
        ),
        "intent_count": len(intent_rows),
    }
