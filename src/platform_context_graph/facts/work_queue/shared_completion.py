"""Helpers for authoritative shared-projection completion state."""

from __future__ import annotations

from typing import Any

from .models import FactWorkItemRow
from .support import utc_now

_RETURNING_COLUMNS = """
RETURNING work_item_id,
          work_type,
          repository_id,
          source_run_id,
          lease_owner,
          lease_expires_at,
          status,
          attempt_count,
          last_error,
          failure_stage,
          error_class,
          failure_class,
          failure_code,
          retry_disposition,
          dead_lettered_at,
          last_attempt_started_at,
          last_attempt_finished_at,
          next_retry_at,
          operator_note,
          parent_work_item_id,
          projection_domain,
          accepted_generation_id,
          authoritative_shared_domains,
          completed_shared_domains,
          shared_projection_pending,
          created_at,
          updated_at
"""


def _normalized_domains(domains: list[str] | tuple[str, ...]) -> list[str]:
    """Return stable unique shared-projection domains."""

    return sorted({domain.strip() for domain in domains if domain.strip()})


def mark_shared_projection_pending(
    queue: Any,
    *,
    work_item_id: str,
    accepted_generation_id: str,
    authoritative_shared_domains: list[str] | tuple[str, ...],
) -> FactWorkItemRow | None:
    """Fence one parent work item until authoritative shared follow-up finishes."""

    domains = _normalized_domains(authoritative_shared_domains)
    if not domains:
        raise ValueError("authoritative_shared_domains must not be empty")
    updated_at = utc_now()
    row = queue._record_operation(
        operation="mark_shared_projection_pending",
        callback=lambda: queue._fetchone(
            f"""
            UPDATE fact_work_items
            SET status = 'awaiting_shared_projection',
                lease_owner = NULL,
                lease_expires_at = NULL,
                accepted_generation_id = %(accepted_generation_id)s,
                authoritative_shared_domains = %(authoritative_shared_domains)s,
                completed_shared_domains = ARRAY[]::TEXT[],
                shared_projection_pending = TRUE,
                last_attempt_finished_at = %(updated_at)s,
                last_attempt_started_at = NULL,
                next_retry_at = NULL,
                updated_at = %(updated_at)s
            WHERE work_item_id = %(work_item_id)s
            {_RETURNING_COLUMNS}
            """,
            {
                "work_item_id": work_item_id,
                "accepted_generation_id": accepted_generation_id,
                "authoritative_shared_domains": domains,
                "updated_at": updated_at,
            },
        ),
    )
    return FactWorkItemRow(**row) if row else None


def complete_shared_projection_domain(
    queue: Any,
    *,
    work_item_id: str,
    projection_domain: str,
    accepted_generation_id: str,
) -> FactWorkItemRow | None:
    """Mark one authoritative shared domain complete for the accepted generation."""

    updated_at = utc_now()
    row = queue._record_operation(
        operation="complete_shared_projection_domain",
        callback=lambda: queue._fetchone(
            f"""
            WITH candidate AS (
                SELECT work_item_id,
                       authoritative_shared_domains,
                       CASE
                           WHEN %(projection_domain)s = ANY(completed_shared_domains)
                               THEN completed_shared_domains
                           ELSE array_append(
                               completed_shared_domains,
                               %(projection_domain)s
                           )
                       END AS next_completed_domains
                FROM fact_work_items
                WHERE work_item_id = %(work_item_id)s
                  AND accepted_generation_id = %(accepted_generation_id)s
                  AND %(projection_domain)s = ANY(authoritative_shared_domains)
            )
            UPDATE fact_work_items AS items
            SET completed_shared_domains = candidate.next_completed_domains,
                shared_projection_pending = EXISTS (
                    SELECT 1
                    FROM unnest(candidate.authoritative_shared_domains) AS domain
                    WHERE NOT domain = ANY(candidate.next_completed_domains)
                ),
                status = CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM unnest(candidate.authoritative_shared_domains) AS domain
                        WHERE NOT domain = ANY(candidate.next_completed_domains)
                    ) THEN 'awaiting_shared_projection'
                    ELSE 'completed'
                END,
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_attempt_finished_at = %(updated_at)s,
                updated_at = %(updated_at)s
            FROM candidate
            WHERE items.work_item_id = candidate.work_item_id
            {_RETURNING_COLUMNS}
            """,
            {
                "work_item_id": work_item_id,
                "projection_domain": projection_domain,
                "accepted_generation_id": accepted_generation_id,
                "updated_at": updated_at,
            },
        ),
    )
    return FactWorkItemRow(**row) if row else None


def complete_shared_projection_domain_by_generation(
    queue: Any,
    *,
    repository_id: str,
    source_run_id: str,
    accepted_generation_id: str,
    projection_domain: str,
) -> FactWorkItemRow | None:
    """Complete one authoritative shared domain by repository/run/generation."""

    updated_at = utc_now()
    row = queue._record_operation(
        operation="complete_shared_projection_domain_by_generation",
        callback=lambda: queue._fetchone(
            f"""
            WITH candidate AS (
                SELECT work_item_id,
                       authoritative_shared_domains,
                       CASE
                           WHEN %(projection_domain)s = ANY(completed_shared_domains)
                               THEN completed_shared_domains
                           ELSE array_append(
                               completed_shared_domains,
                               %(projection_domain)s
                           )
                       END AS next_completed_domains
                FROM fact_work_items
                WHERE repository_id = %(repository_id)s
                  AND source_run_id = %(source_run_id)s
                  AND accepted_generation_id = %(accepted_generation_id)s
                  AND %(projection_domain)s = ANY(authoritative_shared_domains)
                  AND shared_projection_pending = TRUE
                ORDER BY updated_at DESC, work_item_id DESC
                LIMIT 1
            )
            UPDATE fact_work_items AS items
            SET completed_shared_domains = candidate.next_completed_domains,
                shared_projection_pending = EXISTS (
                    SELECT 1
                    FROM unnest(candidate.authoritative_shared_domains) AS domain
                    WHERE NOT domain = ANY(candidate.next_completed_domains)
                ),
                status = CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM unnest(candidate.authoritative_shared_domains) AS domain
                        WHERE NOT domain = ANY(candidate.next_completed_domains)
                    ) THEN 'awaiting_shared_projection'
                    ELSE 'completed'
                END,
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_attempt_finished_at = %(updated_at)s,
                updated_at = %(updated_at)s
            FROM candidate
            WHERE items.work_item_id = candidate.work_item_id
            {_RETURNING_COLUMNS}
            """,
            {
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "accepted_generation_id": accepted_generation_id,
                "projection_domain": projection_domain,
                "updated_at": updated_at,
            },
        ),
    )
    return FactWorkItemRow(**row) if row else None
