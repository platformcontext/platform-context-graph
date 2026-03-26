"""SQL helpers for relationship generation persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence

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
        UPDATE relationship_generations
        SET status = 'inactive'
        WHERE scope = %(scope)s
          AND status = 'active'
          AND generation_id <> %(generation_id)s
        """,
        {"scope": scope, "generation_id": generation_id},
    )
    cursor.execute(
        """
        UPDATE relationship_generations
        SET status = 'active',
            activated_at = %(activated_at)s
        WHERE generation_id = %(generation_id)s
        """,
        {
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
