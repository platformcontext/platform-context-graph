"""SQL helpers for relationship generation persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence

from .entities import CanonicalEntity, Platform, Repository, WorkloadSubject
from .models import (
    RelationshipCandidate,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
    ResolutionGeneration,
)


def persist_generation_records(
    *,
    cursor: Any,
    generation: ResolutionGeneration,
    created_at: datetime,
    digest_fn: Any,
    checkouts: Sequence[RepositoryCheckout],
    entities: Sequence[CanonicalEntity],
    evidence_facts: Sequence[RelationshipEvidenceFact],
    candidates: Sequence[RelationshipCandidate],
    resolved: Sequence[ResolvedRelationship],
) -> None:
    """Persist one pending resolution generation and its related rows."""

    if checkouts:
        cursor.executemany(
            """
            INSERT INTO relationship_checkouts (
                checkout_id,
                logical_repo_id,
                repo_name,
                repo_slug,
                remote_url,
                checkout_path,
                last_seen_at
            ) VALUES (
                %(checkout_id)s,
                %(logical_repo_id)s,
                %(repo_name)s,
                %(repo_slug)s,
                %(remote_url)s,
                %(checkout_path)s,
                %(last_seen_at)s
            )
            ON CONFLICT (checkout_id) DO UPDATE
            SET logical_repo_id = EXCLUDED.logical_repo_id,
                repo_name = EXCLUDED.repo_name,
                repo_slug = EXCLUDED.repo_slug,
                remote_url = EXCLUDED.remote_url,
                checkout_path = EXCLUDED.checkout_path,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            [
                {
                    "checkout_id": checkout.checkout_id,
                    "logical_repo_id": checkout.logical_repo_id,
                    "repo_name": checkout.repo_name,
                    "repo_slug": checkout.repo_slug,
                    "remote_url": checkout.remote_url,
                    "checkout_path": checkout.checkout_path,
                    "last_seen_at": created_at,
                }
                for checkout in checkouts
            ],
        )

    cursor.execute(
        """
        INSERT INTO relationship_generations (
            generation_id,
            scope,
            run_id,
            status,
            created_at,
            activated_at
        ) VALUES (
            %(generation_id)s,
            %(scope)s,
            %(run_id)s,
            'pending',
            %(created_at)s,
            NULL
        )
        """,
        {
            "generation_id": generation.generation_id,
            "scope": generation.scope,
            "run_id": generation.run_id,
            "created_at": created_at,
        },
    )

    if entities:
        cursor.executemany(
            """
            INSERT INTO relationship_entities (
                entity_id,
                entity_type,
                repository_id,
                subject_type,
                kind,
                provider,
                name,
                environment,
                path,
                region,
                locator,
                details,
                created_at,
                updated_at
            ) VALUES (
                %(entity_id)s,
                %(entity_type)s,
                %(repository_id)s,
                %(subject_type)s,
                %(kind)s,
                %(provider)s,
                %(name)s,
                %(environment)s,
                %(path)s,
                %(region)s,
                %(locator)s,
                %(details)s::jsonb,
                %(created_at)s,
                %(updated_at)s
            )
            ON CONFLICT (entity_id) DO UPDATE
            SET entity_type = EXCLUDED.entity_type,
                repository_id = EXCLUDED.repository_id,
                subject_type = EXCLUDED.subject_type,
                kind = EXCLUDED.kind,
                provider = EXCLUDED.provider,
                name = EXCLUDED.name,
                environment = EXCLUDED.environment,
                path = EXCLUDED.path,
                region = EXCLUDED.region,
                locator = EXCLUDED.locator,
                details = EXCLUDED.details,
                updated_at = EXCLUDED.updated_at
            """,
            [_entity_row(entity=entity, created_at=created_at) for entity in entities],
        )

    if evidence_facts:
        cursor.executemany(
            """
            INSERT INTO relationship_evidence_facts (
                evidence_id,
                generation_id,
                evidence_kind,
                relationship_type,
                source_repo_id,
                target_repo_id,
                source_entity_id,
                target_entity_id,
                confidence,
                rationale,
                details,
                observed_at
            ) VALUES (
                %(evidence_id)s,
                %(generation_id)s,
                %(evidence_kind)s,
                %(relationship_type)s,
                %(source_repo_id)s,
                %(target_repo_id)s,
                %(source_entity_id)s,
                %(target_entity_id)s,
                %(confidence)s,
                %(rationale)s,
                %(details)s::jsonb,
                %(observed_at)s
            )
            """,
            [
                {
                    "evidence_id": digest_fn(
                        "evidence",
                        generation.generation_id,
                        fact.relationship_type,
                        fact.evidence_kind,
                        fact.source_repo_id,
                        fact.target_repo_id,
                        json.dumps(fact.details, sort_keys=True),
                    ),
                    "generation_id": generation.generation_id,
                    "evidence_kind": fact.evidence_kind,
                    "relationship_type": fact.relationship_type,
                    "source_repo_id": fact.source_repo_id,
                    "target_repo_id": fact.target_repo_id,
                    "source_entity_id": fact.source_entity_id or fact.source_repo_id,
                    "target_entity_id": fact.target_entity_id or fact.target_repo_id,
                    "confidence": fact.confidence,
                    "rationale": fact.rationale,
                    "details": json.dumps(fact.details, sort_keys=True),
                    "observed_at": created_at,
                }
                for fact in evidence_facts
            ],
        )

    if candidates:
        cursor.executemany(
            """
            INSERT INTO relationship_candidates (
                candidate_id,
                generation_id,
                source_repo_id,
                target_repo_id,
                source_entity_id,
                target_entity_id,
                relationship_type,
                confidence,
                evidence_count,
                rationale,
                details
            ) VALUES (
                %(candidate_id)s,
                %(generation_id)s,
                %(source_repo_id)s,
                %(target_repo_id)s,
                %(source_entity_id)s,
                %(target_entity_id)s,
                %(relationship_type)s,
                %(confidence)s,
                %(evidence_count)s,
                %(rationale)s,
                %(details)s::jsonb
            )
            """,
            [
                {
                    "candidate_id": digest_fn(
                        "candidate",
                        generation.generation_id,
                        candidate.relationship_type,
                        candidate.source_repo_id,
                        candidate.target_repo_id,
                    ),
                    "generation_id": generation.generation_id,
                    "source_repo_id": candidate.source_repo_id,
                    "target_repo_id": candidate.target_repo_id,
                    "source_entity_id": candidate.source_entity_id
                    or candidate.source_repo_id,
                    "target_entity_id": candidate.target_entity_id
                    or candidate.target_repo_id,
                    "relationship_type": candidate.relationship_type,
                    "confidence": candidate.confidence,
                    "evidence_count": candidate.evidence_count,
                    "rationale": candidate.rationale,
                    "details": json.dumps(candidate.details, sort_keys=True),
                }
                for candidate in candidates
            ],
        )

    if resolved:
        cursor.executemany(
            """
            INSERT INTO resolved_relationships (
                generation_id,
                source_repo_id,
                target_repo_id,
                source_entity_id,
                target_entity_id,
                relationship_type,
                confidence,
                evidence_count,
                rationale,
                resolution_source,
                details
            ) VALUES (
                %(generation_id)s,
                %(source_repo_id)s,
                %(target_repo_id)s,
                %(source_entity_id)s,
                %(target_entity_id)s,
                %(relationship_type)s,
                %(confidence)s,
                %(evidence_count)s,
                %(rationale)s,
                %(resolution_source)s,
                %(details)s::jsonb
            )
            """,
            [
                {
                    "generation_id": generation.generation_id,
                    "source_repo_id": item.source_repo_id,
                    "target_repo_id": item.target_repo_id,
                    "source_entity_id": item.source_entity_id or item.source_repo_id,
                    "target_entity_id": item.target_entity_id or item.target_repo_id,
                    "relationship_type": item.relationship_type,
                    "confidence": item.confidence,
                    "evidence_count": item.evidence_count,
                    "rationale": item.rationale,
                    "resolution_source": item.resolution_source,
                    "details": json.dumps(item.details, sort_keys=True),
                }
                for item in resolved
            ],
        )


def activate_generation_record(
    *,
    cursor: Any,
    scope: str,
    generation_id: str,
    activated_at: datetime,
) -> None:
    """Promote one pending generation to active and demote the previous active row."""

    cursor.execute(
        """
        WITH target AS (
            SELECT generation_id
            FROM relationship_generations
            WHERE generation_id = %(generation_id)s
              AND scope = %(scope)s
        )
        UPDATE relationship_generations
        SET status = CASE
                WHEN relationship_generations.generation_id = %(generation_id)s
                    THEN 'active'
                ELSE 'inactive'
            END,
            activated_at = CASE
                WHEN relationship_generations.generation_id = %(generation_id)s
                    THEN %(activated_at)s
                ELSE relationship_generations.activated_at
            END
        WHERE EXISTS (SELECT 1 FROM target)
          AND (
              relationship_generations.generation_id = %(generation_id)s
              OR (
                  relationship_generations.scope = %(scope)s
                  AND relationship_generations.status = 'active'
                  AND relationship_generations.generation_id <> %(generation_id)s
              )
          )
        """,
        {
            "scope": scope,
            "generation_id": generation_id,
            "activated_at": activated_at,
        },
    )


def fetch_active_generation(*, cursor: Any, scope: str) -> ResolutionGeneration | None:
    """Return the active relationship generation for a scope."""

    cursor.execute(
        """
        SELECT generation_id,
               scope,
               run_id,
               status
        FROM relationship_generations
        WHERE scope = %(scope)s
          AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        {"scope": scope},
    )
    row = cursor.fetchone()
    if not row:
        return None
    return ResolutionGeneration(
        generation_id=row["generation_id"],
        scope=row["scope"],
        run_id=row["run_id"],
        status=row["status"],
    )


def _entity_row(*, entity: CanonicalEntity, created_at: datetime) -> dict[str, Any]:
    """Build one additive entity-registry row for persistence."""

    row: dict[str, Any] = {
        "entity_id": entity.entity_id,
        "entity_type": type(entity).__name__,
        "repository_id": None,
        "subject_type": None,
        "kind": None,
        "provider": None,
        "name": entity.name or entity.entity_id,
        "environment": None,
        "path": None,
        "region": None,
        "locator": None,
        "details": json.dumps(entity.details, sort_keys=True),
        "created_at": created_at,
        "updated_at": created_at,
    }
    if isinstance(entity, Repository):
        row["repository_id"] = entity.entity_id
    elif isinstance(entity, Platform):
        row["kind"] = entity.kind
        row["provider"] = entity.provider
        row["environment"] = entity.environment
        row["region"] = entity.region
        row["locator"] = entity.locator
    elif isinstance(entity, WorkloadSubject):
        row["repository_id"] = entity.repository_id
        row["subject_type"] = entity.subject_type
        row["environment"] = entity.environment
        row["path"] = entity.path
    return row
