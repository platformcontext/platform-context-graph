"""PostgreSQL persistence for evidence-backed repository relationships."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import threading
from typing import Any, Mapping, Sequence

from ..observability import get_observability
from ..utils.debug_log import emit_log_call, info_logger
from .entities import CanonicalEntity
from .models import (
    MetadataAssertion,
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
    ResolutionGeneration,
)
from .postgres_generation import (
    activate_generation_record,
    fetch_active_generation,
    persist_generation_records,
)
from .postgres_support import RELATIONSHIP_SCHEMA

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None


def _now() -> datetime:
    """Return the current UTC timestamp for persistence records."""

    return datetime.now(tz=UTC)


def _digest(prefix: str, *parts: str) -> str:
    """Build a stable short identifier from one or more input parts."""

    digest = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def repository_entity_id(repo_id: str) -> str:
    """Return the canonical entity identifier for one repository row."""

    return repo_id


def entity_or_repo_identity(row: Mapping[str, Any], side: str) -> str:
    """Return an explicit entity id or fall back to the repo-backed entity id."""

    return row.get(f"{side}_entity_id") or repository_entity_id(row[f"{side}_repo_id"])


class PostgresRelationshipStore:
    """Persist repository relationship evidence, assertions, and resolutions."""

    def __init__(self, dsn: str) -> None:
        """Initialize the store with a DSN and lazy connection state."""

        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn: Any | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Return whether the store can create live PostgreSQL connections."""

        return psycopg is not None and bool(self._dsn)

    @contextmanager
    def _cursor(self) -> Any:
        """Yield an initialized autocommit cursor for relationship operations."""

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
        entities: Sequence[CanonicalEntity] = (),
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
        observability = get_observability()

        with observability.start_span(
            "pcg.relationships.persist_generation",
            component=observability.component,
            attributes={
                "pcg.relationships.scope": scope,
                "pcg.relationships.run_id": run_id or "adhoc",
                "pcg.relationships.generation_id": generation.generation_id,
                "pcg.relationships.checkout_count": len(checkouts),
                "pcg.relationships.entity_count": len(entities),
                "pcg.relationships.evidence_count": len(evidence_facts),
                "pcg.relationships.candidate_count": len(candidates),
                "pcg.relationships.resolved_count": len(resolved),
            },
        ):
            with self._cursor() as cursor:
                persist_generation_records(
                    cursor=cursor,
                    generation=generation,
                    created_at=created_at,
                    digest_fn=_digest,
                    checkouts=checkouts,
                    entities=entities,
                    evidence_facts=evidence_facts,
                    candidates=candidates,
                    resolved=resolved,
                )
        return generation

    def activate_generation(self, *, scope: str, generation_id: str) -> None:
        """Promote one pending generation to the active generation for a scope."""

        activated_at = _now()
        observability = get_observability()
        with observability.start_span(
            "pcg.relationships.activate_generation",
            component=observability.component,
            attributes={
                "pcg.relationships.scope": scope,
                "pcg.relationships.generation_id": generation_id,
            },
        ):
            with self._cursor() as cursor:
                activate_generation_record(
                    cursor=cursor,
                    scope=scope,
                    generation_id=generation_id,
                    activated_at=activated_at,
                )
        emit_log_call(
            info_logger,
            "Activated relationship generation",
            event_name="relationships.generation.activated",
            extra_keys={
                "scope": scope,
                "generation_id": generation_id,
            },
        )

    def get_active_generation(self, *, scope: str) -> ResolutionGeneration | None:
        """Return the active generation for one scope when present."""

        with self._cursor() as cursor:
            return fetch_active_generation(
                cursor=cursor,
                scope=scope,
            )

    def list_relationship_assertions(
        self,
        *,
        relationship_type: str | None = None,
    ) -> list[RelationshipAssertion]:
        """Return stored assertions for a relationship type."""

        with self._cursor() as cursor:
            if relationship_type is None:
                cursor.execute("""
                    SELECT source_repo_id,
                           target_repo_id,
                           source_entity_id,
                           target_entity_id,
                           relationship_type,
                           decision,
                           reason,
                           actor
                    FROM relationship_assertions
                    ORDER BY updated_at ASC, created_at ASC
                    """)
            else:
                cursor.execute(
                    """
                    SELECT source_repo_id,
                           target_repo_id,
                           source_entity_id,
                           target_entity_id,
                           relationship_type,
                           decision,
                           reason,
                           actor
                    FROM relationship_assertions
                    WHERE relationship_type = %(relationship_type)s
                    ORDER BY updated_at ASC, created_at ASC
                    """,
                    {"relationship_type": relationship_type},
                )
            rows = cursor.fetchall() or []
        return [
            RelationshipAssertion(
                source_repo_id=row["source_repo_id"],
                target_repo_id=row["target_repo_id"],
                source_entity_id=entity_or_repo_identity(row, "source"),
                target_entity_id=entity_or_repo_identity(row, "target"),
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
        )
        observability = get_observability()
        with observability.start_span(
            "pcg.relationships.upsert_assertion",
            component=observability.component,
            attributes={
                "pcg.relationships.relationship_type": assertion.relationship_type,
                "pcg.relationships.decision": assertion.decision,
            },
        ):
            with self._cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO relationship_assertions (
                        assertion_id,
                        source_repo_id,
                        target_repo_id,
                        source_entity_id,
                        target_entity_id,
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
                        %(source_entity_id)s,
                        %(target_entity_id)s,
                        %(relationship_type)s,
                        %(decision)s,
                        %(reason)s,
                        %(actor)s,
                        %(created_at)s,
                        %(updated_at)s
                    )
                    ON CONFLICT (assertion_id) DO UPDATE
                    SET source_entity_id = EXCLUDED.source_entity_id,
                        target_entity_id = EXCLUDED.target_entity_id,
                        decision = EXCLUDED.decision,
                        reason = EXCLUDED.reason,
                        actor = EXCLUDED.actor,
                        updated_at = EXCLUDED.updated_at
                    """,
                    {
                        "assertion_id": assertion_id,
                        "source_repo_id": assertion.source_repo_id,
                        "target_repo_id": assertion.target_repo_id,
                        "source_entity_id": assertion.source_entity_id
                        or repository_entity_id(assertion.source_repo_id),
                        "target_entity_id": assertion.target_entity_id
                        or repository_entity_id(assertion.target_repo_id),
                        "relationship_type": assertion.relationship_type,
                        "decision": assertion.decision,
                        "reason": assertion.reason,
                        "actor": assertion.actor,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
        emit_log_call(
            info_logger,
            "Upserted relationship assertion",
            event_name="relationships.assertion.upserted",
            extra_keys={
                "relationship_type": assertion.relationship_type,
                "decision": assertion.decision,
                "actor": assertion.actor,
                "source_repo_id": assertion.source_repo_id,
                "target_repo_id": assertion.target_repo_id,
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
        observability = get_observability()
        with observability.start_span(
            "pcg.relationships.upsert_metadata_assertion",
            component=observability.component,
            attributes={
                "pcg.relationships.subject_type": assertion.subject_type,
                "pcg.relationships.key": assertion.key,
            },
        ):
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
        emit_log_call(
            info_logger,
            "Upserted metadata assertion",
            event_name="relationships.metadata_assertion.upserted",
            extra_keys={
                "subject_type": assertion.subject_type,
                "subject_id": assertion.subject_id,
                "key": assertion.key,
                "actor": assertion.actor,
            },
        )

    def list_resolved_relationships(self, *, scope: str) -> list[ResolvedRelationship]:
        """Return resolved relationships for the active generation in a scope."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT resolved.source_repo_id,
                       resolved.target_repo_id,
                       resolved.source_entity_id,
                       resolved.target_entity_id,
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
                source_entity_id=entity_or_repo_identity(row, "source"),
                target_entity_id=entity_or_repo_identity(row, "target"),
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
                       candidates.source_entity_id,
                       candidates.target_entity_id,
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
                source_entity_id=entity_or_repo_identity(row, "source"),
                target_entity_id=entity_or_repo_identity(row, "target"),
                relationship_type=row["relationship_type"],
                confidence=row["confidence"],
                evidence_count=row["evidence_count"],
                rationale=row["rationale"],
                details=row["details"] if isinstance(row["details"], dict) else {},
            )
            for row in rows
        ]

    def close(self) -> None:
        """Close the cached PostgreSQL connection when one is open."""

        if self._conn is not None and not self._conn.closed:
            self._conn.close()
