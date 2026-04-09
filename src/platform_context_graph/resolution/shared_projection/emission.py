"""Helpers for emitting shadow shared projection intents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import SharedProjectionIntentRow
from .models import build_shared_projection_intent

ProjectionContextByRepoId = dict[str, dict[str, str]]


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def _intent_rows_for_platform_domain(
    *,
    created_at: datetime,
    descriptor_rows: list[dict[str, object]],
    projection_context_by_repo_id: ProjectionContextByRepoId,
    projection_domain: str,
) -> list[SharedProjectionIntentRow]:
    """Build one platform-domain intent row per descriptor row."""

    rows: list[SharedProjectionIntentRow] = []
    for descriptor in descriptor_rows:
        repository_id = str(descriptor.get("repo_id") or "")
        platform_id = str(descriptor.get("platform_id") or "")
        if not repository_id or not platform_id:
            continue
        context = projection_context_by_repo_id.get(repository_id)
        if context is None:
            continue
        rows.append(
            build_shared_projection_intent(
                projection_domain=projection_domain,
                partition_key=platform_id,
                repository_id=repository_id,
                source_run_id=context["source_run_id"],
                generation_id=context["generation_id"],
                payload={key: value for key, value in descriptor.items()},
                created_at=created_at,
            )
        )
    return rows


def emit_platform_infra_intents(
    *,
    shared_projection_intent_store: Any | None,
    descriptor_rows: list[dict[str, object]],
    projection_context_by_repo_id: ProjectionContextByRepoId | None,
    created_at: datetime | None = None,
) -> None:
    """Persist shadow infrastructure-platform intents when a store is configured."""

    if shared_projection_intent_store is None or not projection_context_by_repo_id:
        return
    rows = _intent_rows_for_platform_domain(
        created_at=created_at or _utc_now(),
        descriptor_rows=descriptor_rows,
        projection_context_by_repo_id=projection_context_by_repo_id,
        projection_domain="platform_infra",
    )
    if rows:
        shared_projection_intent_store.upsert_intents(rows)


def emit_platform_runtime_intents(
    *,
    shared_projection_intent_store: Any | None,
    runtime_platform_rows: list[dict[str, object]],
    projection_context_by_repo_id: ProjectionContextByRepoId | None,
    created_at: datetime | None = None,
) -> None:
    """Persist shadow runtime-platform intents when a store is configured."""

    if shared_projection_intent_store is None or not projection_context_by_repo_id:
        return
    rows = _intent_rows_for_platform_domain(
        created_at=created_at or _utc_now(),
        descriptor_rows=runtime_platform_rows,
        projection_context_by_repo_id=projection_context_by_repo_id,
        projection_domain="platform_runtime",
    )
    if rows:
        shared_projection_intent_store.upsert_intents(rows)


def emit_dependency_intents(
    *,
    shared_projection_intent_store: Any | None,
    repo_dependency_rows: list[dict[str, object]],
    workload_dependency_rows: list[dict[str, object]],
    projection_context_by_repo_id: ProjectionContextByRepoId | None,
    created_at: datetime | None = None,
) -> None:
    """Persist shadow dependency intents when a store is configured."""

    if shared_projection_intent_store is None or not projection_context_by_repo_id:
        return
    created = created_at or _utc_now()
    rows: list[SharedProjectionIntentRow] = []
    for row in repo_dependency_rows:
        repository_id = str(row.get("repo_id") or "")
        target_repo_id = str(row.get("target_repo_id") or "")
        context = projection_context_by_repo_id.get(repository_id)
        if not repository_id or not target_repo_id or context is None:
            continue
        rows.append(
            build_shared_projection_intent(
                projection_domain="repo_dependency",
                partition_key=f"repo:{repository_id}->{target_repo_id}",
                repository_id=repository_id,
                source_run_id=context["source_run_id"],
                generation_id=context["generation_id"],
                payload={key: value for key, value in row.items()},
                created_at=created,
            )
        )
    for row in workload_dependency_rows:
        repository_id = str(row.get("repo_id") or "")
        workload_id = str(row.get("workload_id") or "")
        target_workload_id = str(row.get("target_workload_id") or "")
        context = projection_context_by_repo_id.get(repository_id)
        if (
            not repository_id
            or not workload_id
            or not target_workload_id
            or context is None
        ):
            continue
        rows.append(
            build_shared_projection_intent(
                projection_domain="workload_dependency",
                partition_key=f"workload:{workload_id}->{target_workload_id}",
                repository_id=repository_id,
                source_run_id=context["source_run_id"],
                generation_id=context["generation_id"],
                payload={key: value for key, value in row.items()},
                created_at=created,
            )
        )
    if rows:
        shared_projection_intent_store.upsert_intents(rows)


__all__ = [
    "emit_dependency_intents",
    "emit_platform_infra_intents",
    "emit_platform_runtime_intents",
]
