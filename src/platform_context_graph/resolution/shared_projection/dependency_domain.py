"""Helpers for dependency-domain shared projection cutover."""

from __future__ import annotations

from typing import Any

from .emission import _utc_now
from .models import SharedProjectionIntentRow
from .models import build_shared_projection_intent


def existing_repo_dependency_rows(
    session: Any,
    *,
    repo_ids: list[str],
    evidence_source: str,
) -> list[dict[str, str]]:
    """Return existing repository dependency edges for targeted repositories."""

    if not repo_ids:
        return []
    return session.run(
        """
        MATCH (repo:Repository)-[rel:DEPENDS_ON]->(target_repo:Repository)
        WHERE repo.id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        RETURN repo.id as repo_id,
               target_repo.id as target_repo_id
        ORDER BY repo.id, target_repo.id
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    ).data()


def existing_workload_dependency_rows(
    session: Any,
    *,
    repo_ids: list[str],
    evidence_source: str,
) -> list[dict[str, str]]:
    """Return existing workload dependency edges for targeted repositories."""

    if not repo_ids:
        return []
    return session.run(
        """
        MATCH (source:Workload)-[rel:DEPENDS_ON]->(target:Workload)
        WHERE source.repo_id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        RETURN source.repo_id as repo_id,
               source.id as workload_id,
               target.id as target_workload_id
        ORDER BY source.repo_id, source.id, target.id
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    ).data()


def _build_dependency_intents(
    *,
    projection_domain: str,
    desired_rows: list[dict[str, object]],
    existing_pairs: set[tuple[str, ...]],
    projection_context_by_repo_id: dict[str, dict[str, str]] | None,
    desired_pair_fields: tuple[str, ...],
) -> list[SharedProjectionIntentRow]:
    """Return authoritative upsert and retract intents for one dependency domain."""

    if not projection_context_by_repo_id:
        return []
    created_at = _utc_now()
    desired_pairs = {
        tuple(str(row.get(field) or "") for field in desired_pair_fields)
        for row in desired_rows
    }
    rows: list[SharedProjectionIntentRow] = []
    for row in desired_rows:
        repository_id = str(row.get("repo_id") or "")
        context = projection_context_by_repo_id.get(repository_id)
        partition_key = str(row.get("partition_key") or "")
        if not repository_id or not context or not partition_key:
            continue
        rows.append(
            build_shared_projection_intent(
                projection_domain=projection_domain,
                partition_key=partition_key,
                repository_id=repository_id,
                source_run_id=context["source_run_id"],
                generation_id=context["generation_id"],
                payload={**row, "action": "upsert"},
                created_at=created_at,
            )
        )
    for pair in sorted(existing_pairs - desired_pairs):
        repository_id = pair[0]
        context = projection_context_by_repo_id.get(repository_id)
        if not context:
            continue
        payload = {
            field: value for field, value in zip(desired_pair_fields, pair, strict=True)
        }
        rows.append(
            build_shared_projection_intent(
                projection_domain=projection_domain,
                partition_key=str(payload["partition_key"]),
                repository_id=repository_id,
                source_run_id=context["source_run_id"],
                generation_id=context["generation_id"],
                payload={**payload, "action": "retract"},
                created_at=created_at,
            )
        )
    return rows


def build_repo_dependency_intent_rows(
    *,
    repo_dependency_rows: list[dict[str, object]],
    existing_rows: list[dict[str, str]],
    projection_context_by_repo_id: dict[str, dict[str, str]] | None,
) -> list[SharedProjectionIntentRow]:
    """Return authoritative repository dependency intents."""

    normalized_rows = [
        {
            **row,
            "partition_key": (
                f"repo:{row['repo_id']}->{row['target_repo_id']}"
                if row.get("repo_id") and row.get("target_repo_id")
                else ""
            ),
        }
        for row in repo_dependency_rows
    ]
    existing_pairs = {
        (
            str(row.get("repo_id") or ""),
            str(row.get("target_repo_id") or ""),
            (
                f"repo:{row['repo_id']}->{row['target_repo_id']}"
                if row.get("repo_id") and row.get("target_repo_id")
                else ""
            ),
        )
        for row in existing_rows
    }
    return _build_dependency_intents(
        projection_domain="repo_dependency",
        desired_rows=normalized_rows,
        existing_pairs=existing_pairs,
        projection_context_by_repo_id=projection_context_by_repo_id,
        desired_pair_fields=("repo_id", "target_repo_id", "partition_key"),
    )


def build_workload_dependency_intent_rows(
    *,
    workload_dependency_rows: list[dict[str, object]],
    existing_rows: list[dict[str, str]],
    projection_context_by_repo_id: dict[str, dict[str, str]] | None,
) -> list[SharedProjectionIntentRow]:
    """Return authoritative workload dependency intents."""

    normalized_rows = [
        {
            **row,
            "partition_key": (
                f"workload:{row['workload_id']}->{row['target_workload_id']}"
                if row.get("workload_id") and row.get("target_workload_id")
                else ""
            ),
        }
        for row in workload_dependency_rows
    ]
    existing_pairs = {
        (
            str(row.get("repo_id") or ""),
            str(row.get("workload_id") or ""),
            str(row.get("target_workload_id") or ""),
            (
                f"workload:{row['workload_id']}->{row['target_workload_id']}"
                if row.get("workload_id") and row.get("target_workload_id")
                else ""
            ),
        )
        for row in existing_rows
    }
    return _build_dependency_intents(
        projection_domain="workload_dependency",
        desired_rows=normalized_rows,
        existing_pairs=existing_pairs,
        projection_context_by_repo_id=projection_context_by_repo_id,
        desired_pair_fields=(
            "repo_id",
            "workload_id",
            "target_workload_id",
            "partition_key",
        ),
    )


def shared_dependency_projection_metrics(
    *,
    intent_rows: list[SharedProjectionIntentRow],
    projection_context_by_repo_id: dict[str, dict[str, str]] | None,
) -> dict[str, object]:
    """Return completion-fencing metadata for authoritative dependency cutover."""

    touched_repositories = {
        row.repository_id for row in intent_rows if row.repository_id.strip()
    }
    if not touched_repositories or not projection_context_by_repo_id:
        return {}
    generation_ids = {
        projection_context_by_repo_id[repo_id]["generation_id"]
        for repo_id in touched_repositories
        if repo_id in projection_context_by_repo_id
    }
    domains = sorted(
        {row.projection_domain for row in intent_rows if row.projection_domain}
    )
    return {
        "authoritative_domains": domains,
        "accepted_generation_id": (
            next(iter(generation_ids)) if len(generation_ids) == 1 else None
        ),
        "intent_count": len(intent_rows),
    }


__all__ = [
    "build_repo_dependency_intent_rows",
    "build_workload_dependency_intent_rows",
    "existing_repo_dependency_rows",
    "existing_workload_dependency_rows",
    "shared_dependency_projection_metrics",
]
