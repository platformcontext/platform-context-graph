"""PostgreSQL persistence for evidence-backed repository relationships."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import threading
from typing import Any, Sequence

from ..observability import get_observability
from .models import (
    MetadataAssertion,
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
    ResolutionGeneration,
)
from .postgres_support import RELATIONSHIP_SCHEMA

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _digest(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class PostgresRelationshipStore:
    """Persist repository relationship evidence, assertions, and resolutions."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn: Any | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return psycopg is not None and bool(self._dsn)

    @contextmanager
    def _cursor(self) -> Any:
        if not self.enabled:
            raise RuntimeError("relationship store requires psycopg and a DSN")

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            if not self._initialized:
                with self._conn.cursor() as cursor:
                    cursor.execute(RELATIONSHIP_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def replace_generation(
        self,
        *,
        scope: str,
        run_id: str | None,
        checkouts: Sequence[RepositoryCheckout],
        evidence_facts: Sequence[RelationshipEvidenceFact],
        candidates: Sequence[RelationshipCandidate],
        resolved: Sequence[ResolvedRelationship],
    ) -> ResolutionGeneration:
        """Persist one replacement generation in pending state for a scope."""

        generation = ResolutionGeneration(
            generation_id=_digest(
                "generation", scope, run_id or "", str(_now().timestamp())
            ),
            scope=scope,
            run_id=run_id,
            status="pending",
        )
        created_at = _now()

        with get_observability().start_span(
            "pcg.relationships.postgres.replace_generation",
            attributes={
                "pcg.relationships.scope": scope,
                "pcg.relationships.evidence_count": len(evidence_facts),
                "pcg.relationships.candidate_count": len(candidates),
                "pcg.relationships.resolved_count": len(resolved),
            },
        ):
            with self._cursor() as cursor:
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
                        "scope": scope,
                        "run_id": run_id,
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
                                "evidence_id": _digest(
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
                                "candidate_id": _digest(
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
                                "details": json.dumps(
                                    candidate.details, sort_keys=True
                                ),
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
        return generation

    def activate_generation(self, *, scope: str, generation_id: str) -> None:
        """Promote one pending generation to the active generation for a scope."""

        activated_at = _now()
        with self._cursor() as cursor:
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

    def get_active_generation(self, *, scope: str) -> ResolutionGeneration | None:
        """Return the active generation for one scope when present."""

        with self._cursor() as cursor:
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

    def list_relationship_assertions(
        self,
        *,
        relationship_type: str,
    ) -> list[RelationshipAssertion]:
        """Return stored assertions for a relationship type."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT source_repo_id,
                       target_repo_id,
                       relationship_type,
                       decision,
                       reason,
                       actor
                FROM relationship_assertions
                WHERE relationship_type = %(relationship_type)s
                ORDER BY created_at ASC
                """,
                {"relationship_type": relationship_type},
            )
            rows = cursor.fetchall() or []
        return [
            RelationshipAssertion(
                source_repo_id=row["source_repo_id"],
                target_repo_id=row["target_repo_id"],
                relationship_type=row["relationship_type"],
                decision=row["decision"],
                reason=row["reason"],
                actor=row["actor"],
            )
            for row in rows
        ]

    def upsert_relationship_assertion(self, assertion: RelationshipAssertion) -> None:
        """Create or replace one relationship assertion."""

        now = _now()
        assertion_id = _digest(
            "assertion",
            assertion.relationship_type,
            assertion.source_repo_id,
            assertion.target_repo_id,
            assertion.actor,
        )
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO relationship_assertions (
                    assertion_id,
                    source_repo_id,
                    target_repo_id,
                    relationship_type,
                    decision,
                    reason,
                    actor,
                    created_at,
                    updated_at
                ) VALUES (
                    %(assertion_id)s,
                    %(source_repo_id)s,
                    %(target_repo_id)s,
                    %(relationship_type)s,
                    %(decision)s,
                    %(reason)s,
                    %(actor)s,
                    %(created_at)s,
                    %(updated_at)s
                )
                ON CONFLICT (assertion_id) DO UPDATE
                SET decision = EXCLUDED.decision,
                    reason = EXCLUDED.reason,
                    updated_at = EXCLUDED.updated_at
                """,
                {
                    "assertion_id": assertion_id,
                    "source_repo_id": assertion.source_repo_id,
                    "target_repo_id": assertion.target_repo_id,
                    "relationship_type": assertion.relationship_type,
                    "decision": assertion.decision,
                    "reason": assertion.reason,
                    "actor": assertion.actor,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    def upsert_metadata_assertion(self, assertion: MetadataAssertion) -> None:
        """Create or replace one metadata assertion."""

        now = _now()
        assertion_id = _digest(
            "metadata",
            assertion.subject_type,
            assertion.subject_id,
            assertion.key,
            assertion.actor,
        )
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO metadata_assertions (
                    assertion_id,
                    subject_type,
                    subject_id,
                    key,
                    value,
                    actor,
                    created_at,
                    updated_at
                ) VALUES (
                    %(assertion_id)s,
                    %(subject_type)s,
                    %(subject_id)s,
                    %(key)s,
                    %(value)s,
                    %(actor)s,
                    %(created_at)s,
                    %(updated_at)s
                )
                ON CONFLICT (assertion_id) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
                """,
                {
                    "assertion_id": assertion_id,
                    "subject_type": assertion.subject_type,
                    "subject_id": assertion.subject_id,
                    "key": assertion.key,
                    "value": assertion.value,
                    "actor": assertion.actor,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    def list_resolved_relationships(self, *, scope: str) -> list[ResolvedRelationship]:
        """Return resolved relationships for the active generation in a scope."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT resolved.source_repo_id,
                       resolved.target_repo_id,
                       resolved.relationship_type,
                       resolved.confidence,
                       resolved.evidence_count,
                       resolved.rationale,
                       resolved.resolution_source,
                       resolved.details
                FROM resolved_relationships AS resolved
                JOIN relationship_generations AS generations
                  ON generations.generation_id = resolved.generation_id
                WHERE generations.scope = %(scope)s
                  AND generations.status = 'active'
                ORDER BY resolved.source_repo_id, resolved.target_repo_id
                """,
                {"scope": scope},
            )
            rows = cursor.fetchall() or []
        return [
            ResolvedRelationship(
                source_repo_id=row["source_repo_id"],
                target_repo_id=row["target_repo_id"],
                relationship_type=row["relationship_type"],
                confidence=row["confidence"],
                evidence_count=row["evidence_count"],
                rationale=row["rationale"],
                resolution_source=row["resolution_source"],
                details=row["details"] if isinstance(row["details"], dict) else {},
            )
            for row in rows
        ]

    def list_relationship_candidates(
        self,
        *,
        scope: str,
        relationship_type: str | None = None,
    ) -> list[RelationshipCandidate]:
        """Return relationship candidates for the active generation in a scope."""

        where_clause = (
            "WHERE generations.scope = %(scope)s AND generations.status = 'active'"
        )
        params: dict[str, Any] = {"scope": scope}
        if relationship_type:
            where_clause += " AND candidates.relationship_type = %(relationship_type)s"
            params["relationship_type"] = relationship_type

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                SELECT candidates.source_repo_id,
                       candidates.target_repo_id,
                       candidates.relationship_type,
                       candidates.confidence,
                       candidates.evidence_count,
                       candidates.rationale,
                       candidates.details
                FROM relationship_candidates AS candidates
                JOIN relationship_generations AS generations
                  ON generations.generation_id = candidates.generation_id
                {where_clause}
                ORDER BY candidates.source_repo_id, candidates.target_repo_id
                """,
                params,
            )
            rows = cursor.fetchall() or []
        return [
            RelationshipCandidate(
                source_repo_id=row["source_repo_id"],
                target_repo_id=row["target_repo_id"],
                relationship_type=row["relationship_type"],
                confidence=row["confidence"],
                evidence_count=row["evidence_count"],
                rationale=row["rationale"],
                details=row["details"] if isinstance(row["details"], dict) else {},
            )
            for row in rows
        ]

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
