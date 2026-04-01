"""Evidence-backed repository dependency resolution and orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from ..observability import get_observability
from ..utils.debug_log import emit_log_call, error_logger
from .entities import CanonicalEntity, Repository, entity_from_id
from .execution import (
    REPOSITORY_DEPENDENCY_SCOPE,
    build_repository_checkouts,
    discover_repository_dependency_evidence,
    project_resolved_relationships,
)
from .models import (
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
)
from .platform_resolution import resolve_entity_relationships
from .state import get_relationship_store

_INFERRED_CONFIDENCE_THRESHOLD = 0.75


def dedupe_relationship_evidence_facts(
    evidence_facts: Sequence[RelationshipEvidenceFact],
) -> list[RelationshipEvidenceFact]:
    """Collapse exact duplicate evidence facts while preserving discovery order."""

    deduped: list[RelationshipEvidenceFact] = []
    seen: set[tuple[str, str, str | None, str | None, str | None, str | None, float, str, str]] = set()
    for fact in evidence_facts:
        key = (
            fact.relationship_type,
            fact.evidence_kind,
            fact.source_repo_id,
            fact.target_repo_id,
            fact.source_entity_id,
            fact.target_entity_id,
            fact.confidence,
            fact.rationale,
            json.dumps(fact.details, sort_keys=True),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def resolve_repository_relationships(
    evidence_facts: Sequence[RelationshipEvidenceFact],
    assertions: Sequence[RelationshipAssertion],
    *,
    inferred_confidence_threshold: float = _INFERRED_CONFIDENCE_THRESHOLD,
) -> tuple[list[RelationshipCandidate], list[ResolvedRelationship]]:
    """Resolve raw evidence plus assertions into canonical mixed-entity relationships."""

    return resolve_entity_relationships(
        evidence_facts,
        assertions,
        inferred_confidence_threshold=inferred_confidence_threshold,
    )


def resolve_repository_relationships_for_committed_repositories(
    *,
    builder: Any,
    committed_repo_paths: Sequence[Path],
    run_id: str | None,
    info_logger_fn: Any,
) -> dict[str, int]:
    """Discover, resolve, persist, and project repo dependencies after ingest."""

    store = get_relationship_store()
    if store is None or not store.enabled:
        emit_log_call(
            info_logger_fn,
            "Relationship resolution skipped: Postgres relationship store is not configured",
            event_name="relationships.resolve.skipped",
            extra_keys={
                "scope": REPOSITORY_DEPENDENCY_SCOPE,
                "run_id": run_id or "adhoc",
            },
        )
        return {
            "checkouts": 0,
            "evidence_facts": 0,
            "candidates": 0,
            "resolved_relationships": 0,
        }

    observability = get_observability()
    with observability.start_span(
        "pcg.relationships.resolve_repository_dependencies",
        component=observability.component,
        attributes={
            "pcg.relationships.scope": REPOSITORY_DEPENDENCY_SCOPE,
            "pcg.relationships.run_id": run_id or "adhoc",
            "pcg.relationships.repo_count": len(committed_repo_paths),
        },
    ) as resolve_span:
        emit_log_call(
            info_logger_fn,
            "Resolving repository dependencies from committed repositories",
            event_name="relationships.resolve.started",
            extra_keys={
                "scope": REPOSITORY_DEPENDENCY_SCOPE,
                "run_id": run_id or "adhoc",
                "repo_count": len(committed_repo_paths),
            },
        )
        try:
            checkouts = build_repository_checkouts(committed_repo_paths)
            evidence_facts = discover_repository_dependency_evidence(
                builder.driver,
                checkouts=checkouts,
            )
            evidence_facts = dedupe_relationship_evidence_facts(evidence_facts)
            assertions = store.list_relationship_assertions()
            candidates, resolved = resolve_repository_relationships(
                evidence_facts,
                assertions,
            )
            entities = collect_canonical_entities(
                checkouts=checkouts,
                evidence_facts=evidence_facts,
                candidates=candidates,
                resolved=resolved,
            )
            generation = store.replace_generation(
                scope=REPOSITORY_DEPENDENCY_SCOPE,
                run_id=run_id,
                checkouts=checkouts,
                entities=entities,
                evidence_facts=evidence_facts,
                candidates=candidates,
                resolved=resolved,
            )
            if resolve_span is not None:
                resolve_span.set_attribute(
                    "pcg.relationships.generation_id",
                    generation.generation_id,
                )
                resolve_span.set_attribute(
                    "pcg.relationships.checkout_count",
                    len(checkouts),
                )
                resolve_span.set_attribute(
                    "pcg.relationships.entity_count",
                    len(entities),
                )
                resolve_span.set_attribute(
                    "pcg.relationships.evidence_count",
                    len(evidence_facts),
                )
                resolve_span.set_attribute(
                    "pcg.relationships.candidate_count",
                    len(candidates),
                )
                resolve_span.set_attribute(
                    "pcg.relationships.resolved_count",
                    len(resolved),
                )
            emit_log_call(
                info_logger_fn,
                "Persisted pending repository relationship generation",
                event_name="relationships.persist_generation.completed",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "run_id": run_id or "adhoc",
                    "generation_id": generation.generation_id,
                    "entity_count": len(entities),
                    "candidate_count": len(candidates),
                    "resolved_count": len(resolved),
                },
            )
            committed_repo_ids = [c.logical_repo_id for c in checkouts]
            project_resolved_relationships(
                db_manager=builder.db_manager,
                generation_id=generation.generation_id,
                resolved=resolved,
                committed_repo_ids=committed_repo_ids,
            )
            emit_log_call(
                info_logger_fn,
                "Projected resolved repository relationships into the graph",
                event_name="relationships.project.completed",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "run_id": run_id or "adhoc",
                    "generation_id": generation.generation_id,
                    "resolved_count": len(resolved),
                },
            )
            store.activate_generation(
                scope=REPOSITORY_DEPENDENCY_SCOPE,
                generation_id=generation.generation_id,
            )
            emit_log_call(
                info_logger_fn,
                "Repository dependency resolution complete",
                event_name="relationships.resolve.completed",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "run_id": run_id or "adhoc",
                    "generation_id": generation.generation_id,
                    "checkout_count": len(checkouts),
                    "evidence_count": len(evidence_facts),
                    "candidate_count": len(candidates),
                    "resolved_count": len(resolved),
                },
            )
            return {
                "checkouts": len(checkouts),
                "evidence_facts": len(evidence_facts),
                "candidates": len(candidates),
                "resolved_relationships": len(resolved),
            }
        except Exception as exc:
            emit_log_call(
                error_logger,
                "Repository dependency resolution failed",
                event_name="relationships.resolve.failed",
                extra_keys={
                    "scope": REPOSITORY_DEPENDENCY_SCOPE,
                    "run_id": run_id or "adhoc",
                    "repo_count": len(committed_repo_paths),
                },
                exc_info=exc,
            )
            raise


def collect_canonical_entities(
    *,
    checkouts: Sequence[RepositoryCheckout],
    evidence_facts: Sequence[RelationshipEvidenceFact],
    candidates: Sequence[RelationshipCandidate],
    resolved: Sequence[ResolvedRelationship],
) -> list[CanonicalEntity]:
    """Collect canonical entities referenced by one resolver generation."""

    entities_by_id: dict[str, CanonicalEntity] = {}
    for checkout in checkouts:
        repository = Repository.from_parts(
            name=checkout.repo_name,
            remote_url=checkout.remote_url,
            local_path=checkout.checkout_path,
            repo_slug=checkout.repo_slug,
        )
        entities_by_id[repository.entity_id] = repository

    def _remember(entity_id: str | None) -> None:
        """Record one canonical entity id when it can be materialized safely."""

        if not entity_id or entity_id in entities_by_id:
            return
        entity = entity_from_id(entity_id)
        if entity is not None:
            entities_by_id[entity.entity_id] = entity

    for fact in evidence_facts:
        _remember(fact.source_entity_id or fact.source_repo_id)
        _remember(fact.target_entity_id or fact.target_repo_id)
    for candidate in candidates:
        _remember(candidate.source_entity_id or candidate.source_repo_id)
        _remember(candidate.target_entity_id or candidate.target_repo_id)
    for relationship in resolved:
        _remember(relationship.source_entity_id or relationship.source_repo_id)
        _remember(relationship.target_entity_id or relationship.target_repo_id)

    return list(entities_by_id.values())


__all__ = [
    "REPOSITORY_DEPENDENCY_SCOPE",
    "build_repository_checkouts",
    "discover_repository_dependency_evidence",
    "project_resolved_relationships",
    "collect_canonical_entities",
    "resolve_entity_relationships",
    "resolve_repository_relationships",
    "resolve_repository_relationships_for_committed_repositories",
]
