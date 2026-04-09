"""Runtime helpers for partitioned shared platform projection."""

from __future__ import annotations

import os
from typing import Any

from .dependency_runtime_support import retract_repo_dependency_edges
from .dependency_runtime_support import retract_workload_dependency_edges
from .dependency_runtime_support import write_repo_dependency_edges
from .dependency_runtime_support import write_workload_dependency_edges
from .partitioning import rows_for_partition

PLATFORM_INFRA_PROJECTION_DOMAIN = "platform_infra"
REPO_DEPENDENCY_PROJECTION_DOMAIN = "repo_dependency"
WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN = "workload_dependency"
DEPENDENCY_PROJECTION_DOMAINS = {
    REPO_DEPENDENCY_PROJECTION_DOMAIN,
    WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
}


def platform_shared_projection_worker_enabled() -> bool:
    """Return whether platform shared-domain workers own authoritative writes."""

    raw = os.getenv("PCG_SHARED_PLATFORM_WORKER_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def dependency_shared_projection_worker_enabled() -> bool:
    """Return whether dependency shared-domain workers own authoritative writes."""

    raw = os.getenv("PCG_SHARED_DEPENDENCY_WORKER_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _latest_intents_by_repo_and_partition(
    intents: list[Any],
) -> tuple[list[Any], list[str]]:
    """Return newest intents and superseded ids per repo/partition pair."""

    latest_by_key: dict[tuple[str, str], Any] = {}
    superseded_ids: list[str] = []
    for intent in sorted(intents, key=lambda row: (row.created_at, row.intent_id)):
        key = (intent.repository_id, intent.partition_key)
        previous = latest_by_key.get(key)
        if previous is not None:
            superseded_ids.append(previous.intent_id)
        latest_by_key[key] = intent
    return list(latest_by_key.values()), superseded_ids


def _accepted_generations_by_repo_run(
    fact_work_queue: Any | None,
    *,
    projection_domain: str,
    repository_ids: list[str],
    accepted_generations_override: dict[tuple[str, str], str] | None = None,
) -> dict[tuple[str, str], str]:
    """Return accepted shared generations keyed by repository and source run."""

    accepted_generations = dict(accepted_generations_override or {})
    if fact_work_queue is None:
        return accepted_generations
    list_fn = getattr(fact_work_queue, "list_shared_projection_acceptances", None)
    if not callable(list_fn):
        return accepted_generations
    accepted = list_fn(
        projection_domain=projection_domain,
        repository_ids=repository_ids or None,
    )
    if not isinstance(accepted, dict):
        return accepted_generations
    accepted_generations.update(
        {
            (str(key[0]), str(key[1])): str(value)
            for key, value in accepted.items()
            if isinstance(key, tuple) and len(key) == 2 and str(value).strip()
        }
    )
    return accepted_generations


def _filter_authoritative_intents(
    intents: list[Any],
    *,
    accepted_generations: dict[tuple[str, str], str],
) -> tuple[list[Any], list[str]]:
    """Split active and stale intents using accepted generation state."""

    active_rows: list[Any] = []
    stale_ids: list[str] = []
    for intent in intents:
        accepted_generation = accepted_generations.get(
            (intent.repository_id, intent.source_run_id)
        )
        if not accepted_generation:
            continue
        if intent.generation_id != accepted_generation:
            stale_ids.append(intent.intent_id)
            continue
        active_rows.append(intent)
    return active_rows, stale_ids


def _retract_platform_edges(
    session: Any,
    *,
    rows: list[dict[str, str]],
    evidence_source: str,
) -> None:
    """Delete targeted repository-platform edges before authoritative replay."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})-[rel:PROVISIONS_PLATFORM]->(
            p:Platform {id: row.platform_id}
        )
        WHERE rel.evidence_source = $evidence_source
        DELETE rel
        """,
        rows=rows,
        evidence_source=evidence_source,
    )


def _write_platform_edges(
    session: Any,
    *,
    rows: list[dict[str, object]],
    evidence_source: str,
) -> None:
    """Authoritatively upsert repository-platform edges for one partition batch."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})
        MERGE (p:Platform {id: row.platform_id})
        ON CREATE SET p.evidence_source = $evidence_source
        SET p.type = 'platform',
            p.name = row.platform_name,
            p.kind = row.platform_kind,
            p.provider = row.platform_provider,
            p.environment = row.platform_environment,
            p.region = row.platform_region,
            p.locator = row.platform_locator
        MERGE (repo)-[rel:PROVISIONS_PLATFORM]->(p)
        SET rel.confidence = 0.98,
            rel.reason = 'Terraform cluster and module data declare platform provisioning',
            rel.evidence_source = $evidence_source
        """,
        rows=rows,
        evidence_source=evidence_source,
    )


def process_platform_partition_once(
    session: Any,
    *,
    shared_projection_intent_store: Any,
    fact_work_queue: Any | None,
    partition_id: int,
    partition_count: int,
    lease_owner: str,
    lease_ttl_seconds: int,
    batch_limit: int = 100,
    evidence_source: str = "finalization/workloads",
    accepted_generations_override: dict[tuple[str, str], str] | None = None,
) -> dict[str, int | bool]:
    """Process one authoritative platform partition exactly once."""

    claimed = shared_projection_intent_store.claim_partition_lease(
        projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
        partition_id=partition_id,
        partition_count=partition_count,
        lease_owner=lease_owner,
        lease_ttl_seconds=lease_ttl_seconds,
    )
    if not claimed:
        return {"lease_acquired": False, "processed_intents": 0}

    try:
        pending_rows = shared_projection_intent_store.list_pending_domain_intents(
            projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
            limit=max(batch_limit, 1) * max(partition_count, 1) * 2,
        )
        partition_rows = rows_for_partition(
            pending_rows,
            partition_id=partition_id,
            partition_count=partition_count,
        )[: max(batch_limit, 1)]
        if not partition_rows:
            return {"lease_acquired": True, "processed_intents": 0}

        accepted_generations = _accepted_generations_by_repo_run(
            fact_work_queue,
            projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
            repository_ids=sorted({row.repository_id for row in partition_rows}),
            accepted_generations_override=accepted_generations_override,
        )
        active_rows, stale_ids = _filter_authoritative_intents(
            partition_rows,
            accepted_generations=accepted_generations,
        )
        latest_rows, superseded_ids = _latest_intents_by_repo_and_partition(active_rows)
        retract_rows = [
            {
                "repo_id": str(intent.payload.get("repo_id") or intent.repository_id),
                "platform_id": str(
                    intent.payload.get("platform_id") or intent.partition_key
                ),
            }
            for intent in latest_rows
        ]
        upsert_rows = [
            dict(intent.payload)
            for intent in latest_rows
            if str(intent.payload.get("action") or "upsert") == "upsert"
        ]

        _retract_platform_edges(
            session,
            rows=retract_rows,
            evidence_source=evidence_source,
        )
        _write_platform_edges(
            session,
            rows=upsert_rows,
            evidence_source=evidence_source,
        )

        processed_ids = (
            stale_ids + superseded_ids + [intent.intent_id for intent in latest_rows]
        )
        shared_projection_intent_store.mark_intents_completed(intent_ids=processed_ids)

        touched_generations = {
            (intent.repository_id, intent.source_run_id, intent.generation_id)
            for intent in latest_rows
        }
        if fact_work_queue is not None and hasattr(
            fact_work_queue, "complete_shared_projection_domain_by_generation"
        ):
            for repository_id, source_run_id, generation_id in sorted(
                touched_generations
            ):
                remaining = shared_projection_intent_store.count_pending_repository_generation_intents(
                    repository_id=repository_id,
                    source_run_id=source_run_id,
                    generation_id=generation_id,
                    projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
                )
                if remaining == 0:
                    fact_work_queue.complete_shared_projection_domain_by_generation(
                        repository_id=repository_id,
                        source_run_id=source_run_id,
                        accepted_generation_id=generation_id,
                        projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
                    )
        return {
            "lease_acquired": True,
            "processed_intents": len(processed_ids),
            "upserted_rows": len(upsert_rows),
            "retracted_rows": len(retract_rows),
        }
    finally:
        shared_projection_intent_store.release_partition_lease(
            projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
            partition_id=partition_id,
            partition_count=partition_count,
            lease_owner=lease_owner,
        )


def process_dependency_partition_once(
    session: Any,
    *,
    shared_projection_intent_store: Any,
    fact_work_queue: Any | None,
    projection_domain: str,
    partition_id: int,
    partition_count: int,
    lease_owner: str,
    lease_ttl_seconds: int,
    batch_limit: int = 100,
    evidence_source: str = "finalization/workloads",
    accepted_generations_override: dict[tuple[str, str], str] | None = None,
) -> dict[str, int | bool]:
    """Process one authoritative dependency partition exactly once."""

    if projection_domain not in DEPENDENCY_PROJECTION_DOMAINS:
        raise ValueError(
            f"unsupported dependency projection domain: {projection_domain}"
        )
    claimed = shared_projection_intent_store.claim_partition_lease(
        projection_domain=projection_domain,
        partition_id=partition_id,
        partition_count=partition_count,
        lease_owner=lease_owner,
        lease_ttl_seconds=lease_ttl_seconds,
    )
    if not claimed:
        return {"lease_acquired": False, "processed_intents": 0}

    try:
        pending_rows = shared_projection_intent_store.list_pending_domain_intents(
            projection_domain=projection_domain,
            limit=max(batch_limit, 1) * max(partition_count, 1) * 2,
        )
        partition_rows = rows_for_partition(
            pending_rows,
            partition_id=partition_id,
            partition_count=partition_count,
        )[: max(batch_limit, 1)]
        if not partition_rows:
            return {"lease_acquired": True, "processed_intents": 0}

        accepted_generations = _accepted_generations_by_repo_run(
            fact_work_queue,
            projection_domain=projection_domain,
            repository_ids=sorted({row.repository_id for row in partition_rows}),
            accepted_generations_override=accepted_generations_override,
        )
        active_rows, stale_ids = _filter_authoritative_intents(
            partition_rows,
            accepted_generations=accepted_generations,
        )
        latest_rows, superseded_ids = _latest_intents_by_repo_and_partition(active_rows)
        if projection_domain == REPO_DEPENDENCY_PROJECTION_DOMAIN:
            retract_rows = [
                {
                    "repo_id": str(
                        intent.payload.get("repo_id") or intent.repository_id
                    ),
                    "target_repo_id": str(intent.payload.get("target_repo_id") or ""),
                }
                for intent in latest_rows
            ]
            upsert_rows = [
                dict(intent.payload)
                for intent in latest_rows
                if str(intent.payload.get("action") or "upsert") == "upsert"
            ]
            retract_repo_dependency_edges(
                session,
                rows=retract_rows,
                evidence_source=evidence_source,
            )
            write_repo_dependency_edges(
                session,
                rows=upsert_rows,
                evidence_source=evidence_source,
            )
        else:
            retract_rows = [
                {
                    "workload_id": str(intent.payload.get("workload_id") or ""),
                    "target_workload_id": str(
                        intent.payload.get("target_workload_id") or ""
                    ),
                }
                for intent in latest_rows
            ]
            upsert_rows = [
                dict(intent.payload)
                for intent in latest_rows
                if str(intent.payload.get("action") or "upsert") == "upsert"
            ]
            retract_workload_dependency_edges(
                session,
                rows=retract_rows,
                evidence_source=evidence_source,
            )
            write_workload_dependency_edges(
                session,
                rows=upsert_rows,
                evidence_source=evidence_source,
            )

        processed_ids = (
            stale_ids + superseded_ids + [intent.intent_id for intent in latest_rows]
        )
        shared_projection_intent_store.mark_intents_completed(intent_ids=processed_ids)

        touched_generations = {
            (intent.repository_id, intent.source_run_id, intent.generation_id)
            for intent in latest_rows
        }
        if fact_work_queue is not None and hasattr(
            fact_work_queue, "complete_shared_projection_domain_by_generation"
        ):
            for repository_id, source_run_id, generation_id in sorted(
                touched_generations
            ):
                remaining = shared_projection_intent_store.count_pending_repository_generation_intents(
                    repository_id=repository_id,
                    source_run_id=source_run_id,
                    generation_id=generation_id,
                    projection_domain=projection_domain,
                )
                if remaining == 0:
                    fact_work_queue.complete_shared_projection_domain_by_generation(
                        repository_id=repository_id,
                        source_run_id=source_run_id,
                        accepted_generation_id=generation_id,
                        projection_domain=projection_domain,
                    )
        return {
            "lease_acquired": True,
            "processed_intents": len(processed_ids),
            "upserted_rows": len(upsert_rows),
            "retracted_rows": len(retract_rows),
        }
    finally:
        shared_projection_intent_store.release_partition_lease(
            projection_domain=projection_domain,
            partition_id=partition_id,
            partition_count=partition_count,
            lease_owner=lease_owner,
        )
