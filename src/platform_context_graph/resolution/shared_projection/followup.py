"""Inline shared-projection follow-up helpers for runtime entrypoints."""

from __future__ import annotations

import os
from typing import Any

from .partitioning import partition_for_key
from .runtime import PLATFORM_INFRA_PROJECTION_DOMAIN
from .runtime import DEPENDENCY_PROJECTION_DOMAINS
from .runtime import process_dependency_partition_once
from .runtime import process_platform_partition_once


def _shared_projection_partition_count() -> int:
    """Return the configured shared-projection partition count."""

    raw_value = os.getenv("PCG_SHARED_PROJECTION_PARTITION_COUNT", "8").strip()
    try:
        return max(int(raw_value), 1)
    except ValueError:
        return 8


def _accepted_override(
    *,
    repository_id: str,
    source_run_id: str,
    accepted_generation_id: str,
) -> dict[tuple[str, str], str]:
    """Build one accepted-generation override map for inline follow-up."""

    generation_id = accepted_generation_id.strip()
    if not generation_id:
        return {}
    return {(repository_id, source_run_id): generation_id}


def _pending_partition_ids(
    *,
    shared_projection_intent_store: Any,
    repository_id: str,
    source_run_id: str,
    projection_domain: str,
    partition_count: int,
) -> list[int] | None:
    """Return pending partition ids for one repository/run/domain page."""

    list_intents = getattr(shared_projection_intent_store, "list_intents", None)
    if not callable(list_intents):
        return None
    pending_rows = [
        row
        for row in list_intents(
            repository_id=repository_id,
            source_run_id=source_run_id,
            projection_domain=projection_domain,
            limit=10_000,
        )
        if getattr(row, "completed_at", None) is None
    ]
    return sorted(
        {
            partition_for_key(
                str(getattr(row, "partition_key", "")),
                partition_count=partition_count,
            )
            for row in pending_rows
            if str(getattr(row, "partition_key", "")).strip()
        }
    )


def run_inline_shared_followup(
    *,
    builder: Any,
    repository_id: str,
    source_run_id: str,
    accepted_generation_id: str,
    authoritative_domains: list[str] | tuple[str, ...],
    fact_work_queue: Any | None,
    shared_projection_intent_store: Any | None,
    lease_owner: str = "inline-shared-followup",
    lease_ttl_seconds: int = 60,
) -> dict[str, object]:
    """Drain authoritative shared domains inline for one repository generation."""

    domains = sorted(
        {str(domain).strip() for domain in authoritative_domains if str(domain).strip()}
    )
    if not domains or shared_projection_intent_store is None:
        return (
            {
                "authoritative_domains": domains,
                "accepted_generation_id": accepted_generation_id,
            }
            if domains
            else {}
        )

    accepted_generations_override = _accepted_override(
        repository_id=repository_id,
        source_run_id=source_run_id,
        accepted_generation_id=accepted_generation_id,
    )
    partition_count = _shared_projection_partition_count()
    remaining_domains: list[str] = []
    count_pending = getattr(
        shared_projection_intent_store,
        "count_pending_repository_generation_intents",
        None,
    )

    with builder.driver.session() as session:
        for domain in domains:
            if not callable(count_pending):
                remaining_domains.append(domain)
                continue
            previous_remaining: int | None = None
            while True:
                partition_ids = _pending_partition_ids(
                    shared_projection_intent_store=shared_projection_intent_store,
                    repository_id=repository_id,
                    source_run_id=source_run_id,
                    projection_domain=domain,
                    partition_count=partition_count,
                )
                if partition_ids is None:
                    remaining_domains.append(domain)
                    break
                if not partition_ids:
                    break
                for partition_id in partition_ids:
                    if domain == PLATFORM_INFRA_PROJECTION_DOMAIN:
                        process_platform_partition_once(
                            session,
                            shared_projection_intent_store=shared_projection_intent_store,
                            fact_work_queue=fact_work_queue,
                            partition_id=partition_id,
                            partition_count=partition_count,
                            lease_owner=lease_owner,
                            lease_ttl_seconds=lease_ttl_seconds,
                            accepted_generations_override=accepted_generations_override,
                        )
                    elif domain in DEPENDENCY_PROJECTION_DOMAINS:
                        process_dependency_partition_once(
                            session,
                            shared_projection_intent_store=shared_projection_intent_store,
                            fact_work_queue=fact_work_queue,
                            projection_domain=domain,
                            partition_id=partition_id,
                            partition_count=partition_count,
                            lease_owner=lease_owner,
                            lease_ttl_seconds=lease_ttl_seconds,
                            accepted_generations_override=accepted_generations_override,
                        )
                remaining = int(
                    count_pending(
                        repository_id=repository_id,
                        source_run_id=source_run_id,
                        generation_id=accepted_generation_id,
                        projection_domain=domain,
                    )
                    or 0
                )
                if remaining <= 0:
                    break
                if previous_remaining is not None and remaining >= previous_remaining:
                    remaining_domains.append(domain)
                    break
                previous_remaining = remaining

    if not remaining_domains:
        return {}
    return {
        "authoritative_domains": remaining_domains,
        "accepted_generation_id": accepted_generation_id,
    }
