"""Evidence-backed repository dependency resolution and orchestration."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from ..observability import get_observability
from ..utils.debug_log import emit_log_call, error_logger
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
    ResolvedRelationship,
)
from .state import get_relationship_store

_INFERRED_CONFIDENCE_THRESHOLD = 0.75


def resolve_repository_relationships(
    evidence_facts: Sequence[RelationshipEvidenceFact],
    assertions: Sequence[RelationshipAssertion],
    *,
    inferred_confidence_threshold: float = _INFERRED_CONFIDENCE_THRESHOLD,
) -> tuple[list[RelationshipCandidate], list[ResolvedRelationship]]:
    """Resolve raw evidence plus assertions into canonical repo dependencies."""

    grouped: dict[tuple[str, str, str], list[RelationshipEvidenceFact]] = defaultdict(
        list
    )
    for fact in evidence_facts:
        grouped[
            (fact.source_repo_id, fact.target_repo_id, fact.relationship_type)
        ].append(fact)

    candidates: list[RelationshipCandidate] = []
    for (source_repo_id, target_repo_id, relationship_type), facts in sorted(
        grouped.items()
    ):
        top_confidence = max(fact.confidence for fact in facts)
        rationale = "; ".join(
            value
            for value in dict.fromkeys(
                fact.rationale for fact in facts if fact.rationale
            )
        )
        candidates.append(
            RelationshipCandidate(
                source_repo_id=source_repo_id,
                target_repo_id=target_repo_id,
                relationship_type=relationship_type,
                confidence=top_confidence,
                evidence_count=len(facts),
                rationale=rationale,
                details={
                    "evidence_kinds": sorted({fact.evidence_kind for fact in facts}),
                    "evidence_preview": [
                        {
                            "kind": fact.evidence_kind,
                            "confidence": fact.confidence,
                            "details": fact.details,
                        }
                        for fact in facts[:5]
                    ],
                },
            )
        )

    latest_decisions: dict[tuple[str, str, str], RelationshipAssertion] = {}
    for item in assertions:
        latest_decisions[
            (item.source_repo_id, item.target_repo_id, item.relationship_type)
        ] = item

    rejections = {
        key for key, item in latest_decisions.items() if item.decision == "reject"
    }
    explicit_assertions = {
        key: item for key, item in latest_decisions.items() if item.decision == "assert"
    }

    resolved: list[ResolvedRelationship] = []
    for candidate in candidates:
        key = (
            candidate.source_repo_id,
            candidate.target_repo_id,
            candidate.relationship_type,
        )
        if key in rejections or candidate.confidence < inferred_confidence_threshold:
            continue
        resolved.append(
            ResolvedRelationship(
                source_repo_id=candidate.source_repo_id,
                target_repo_id=candidate.target_repo_id,
                relationship_type=candidate.relationship_type,
                confidence=candidate.confidence,
                evidence_count=candidate.evidence_count,
                rationale=candidate.rationale,
                resolution_source="inferred",
                details=dict(candidate.details),
            )
        )

    existing_keys = {
        (item.source_repo_id, item.target_repo_id, item.relationship_type)
        for item in resolved
    }
    for key, assertion in sorted(explicit_assertions.items()):
        if key in rejections:
            continue
        if key in existing_keys:
            resolved = [
                (
                    item
                    if (
                        item.source_repo_id,
                        item.target_repo_id,
                        item.relationship_type,
                    )
                    != key
                    else ResolvedRelationship(
                        source_repo_id=assertion.source_repo_id,
                        target_repo_id=assertion.target_repo_id,
                        relationship_type=assertion.relationship_type,
                        confidence=1.0,
                        evidence_count=item.evidence_count,
                        rationale=assertion.reason,
                        resolution_source="assertion",
                        details={**item.details, "actor": assertion.actor},
                    )
                )
                for item in resolved
            ]
            continue
        resolved.append(
            ResolvedRelationship(
                source_repo_id=assertion.source_repo_id,
                target_repo_id=assertion.target_repo_id,
                relationship_type=assertion.relationship_type,
                confidence=1.0,
                evidence_count=0,
                rationale=assertion.reason,
                resolution_source="assertion",
                details={"actor": assertion.actor},
            )
        )

    resolved.sort(
        key=lambda item: (
            item.source_repo_id,
            item.target_repo_id,
            item.relationship_type,
        )
    )
    return candidates, resolved


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
            evidence_facts = discover_repository_dependency_evidence(builder.driver)
            assertions = store.list_relationship_assertions(
                relationship_type="DEPENDS_ON"
            )
            candidates, resolved = resolve_repository_relationships(
                evidence_facts,
                assertions,
            )
            generation = store.replace_generation(
                scope=REPOSITORY_DEPENDENCY_SCOPE,
                run_id=run_id,
                checkouts=checkouts,
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
                    "candidate_count": len(candidates),
                    "resolved_count": len(resolved),
                },
            )
            project_resolved_relationships(
                db_manager=builder.db_manager,
                generation_id=generation.generation_id,
                resolved=resolved,
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


__all__ = [
    "REPOSITORY_DEPENDENCY_SCOPE",
    "build_repository_checkouts",
    "discover_repository_dependency_evidence",
    "project_resolved_relationships",
    "resolve_repository_relationships",
    "resolve_repository_relationships_for_committed_repositories",
]
