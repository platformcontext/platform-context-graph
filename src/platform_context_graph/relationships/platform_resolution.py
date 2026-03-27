"""Entity-aware relationship resolution helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .models import (
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    ResolvedRelationship,
)
from .platform_resolution_support import (
    derive_direct_generic_relationships,
    derive_platform_chain_dependencies,
    dedupe_resolved_relationships,
    entity_identity,
    preferred_repository_id,
    suppress_generic_relationship_candidates,
)

_INFERRED_CONFIDENCE_THRESHOLD = 0.75


def resolve_entity_relationships(
    evidence_facts: Sequence[RelationshipEvidenceFact],
    assertions: Sequence[RelationshipAssertion],
    *,
    inferred_confidence_threshold: float = _INFERRED_CONFIDENCE_THRESHOLD,
) -> tuple[list[RelationshipCandidate], list[ResolvedRelationship]]:
    """Resolve raw evidence and assertions across mixed entity families."""

    grouped: dict[tuple[str, str, str], list[RelationshipEvidenceFact]] = defaultdict(
        list
    )
    for fact in evidence_facts:
        source_entity_id = entity_identity(
            entity_id=fact.source_entity_id,
            repository_id=fact.source_repo_id,
        )
        target_entity_id = entity_identity(
            entity_id=fact.target_entity_id,
            repository_id=fact.target_repo_id,
        )
        if source_entity_id is None or target_entity_id is None:
            continue
        grouped[(source_entity_id, target_entity_id, fact.relationship_type)].append(fact)

    candidates = suppress_generic_relationship_candidates(
        [
            _build_candidate(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=relationship_type,
                facts=facts,
            )
            for (source_entity_id, target_entity_id, relationship_type), facts in sorted(
                grouped.items()
            )
        ]
    )

    rejections, explicit_assertions = _group_assertions(assertions)
    resolved = [
        _candidate_to_resolved(candidate)
        for candidate in candidates
        if (
            candidate.source_entity_id,
            candidate.target_entity_id,
            candidate.relationship_type,
        )
        not in rejections
        and candidate.confidence >= inferred_confidence_threshold
    ]
    resolved = _apply_explicit_assertions(resolved=resolved, assertions=explicit_assertions)
    resolved.extend(derive_direct_generic_relationships(resolved=resolved, rejections=rejections))
    resolved.extend(
        derive_platform_chain_dependencies(resolved=resolved, rejections=rejections)
    )
    resolved = dedupe_resolved_relationships(resolved)
    resolved.sort(
        key=lambda item: (
            item.source_entity_id or "",
            item.target_entity_id or "",
            item.relationship_type,
        )
    )
    return candidates, resolved


def _build_candidate(
    *,
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    facts: Sequence[RelationshipEvidenceFact],
) -> RelationshipCandidate:
    """Aggregate one grouped evidence bucket into a candidate relationship."""

    return RelationshipCandidate(
        source_repo_id=preferred_repository_id(
            entity_id=source_entity_id,
            repository_ids=[fact.source_repo_id for fact in facts],
        ),
        target_repo_id=preferred_repository_id(
            entity_id=target_entity_id,
            repository_ids=[fact.target_repo_id for fact in facts],
        ),
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
        confidence=max(fact.confidence for fact in facts),
        evidence_count=len(facts),
        rationale="; ".join(
            value
            for value in dict.fromkeys(fact.rationale for fact in facts if fact.rationale)
        ),
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


def _group_assertions(
    assertions: Sequence[RelationshipAssertion],
) -> tuple[
    set[tuple[str, str, str]],
    dict[tuple[str, str, str], RelationshipAssertion],
]:
    """Split assertions into rejection and explicit-assertion maps by entity key."""

    latest_decisions: dict[tuple[str, str, str], RelationshipAssertion] = {}
    for assertion in assertions:
        source_entity_id = entity_identity(
            entity_id=assertion.source_entity_id,
            repository_id=assertion.source_repo_id,
        )
        target_entity_id = entity_identity(
            entity_id=assertion.target_entity_id,
            repository_id=assertion.target_repo_id,
        )
        if source_entity_id is None or target_entity_id is None:
            continue
        latest_decisions[
            (source_entity_id, target_entity_id, assertion.relationship_type)
        ] = assertion

    rejections = {
        key for key, assertion in latest_decisions.items() if assertion.decision == "reject"
    }
    explicit_assertions = {
        key: assertion
        for key, assertion in latest_decisions.items()
        if assertion.decision == "assert"
    }
    return rejections, explicit_assertions


def _candidate_to_resolved(candidate: RelationshipCandidate) -> ResolvedRelationship:
    """Promote one inferred candidate into a resolved relationship."""

    return ResolvedRelationship(
        source_repo_id=candidate.source_repo_id,
        target_repo_id=candidate.target_repo_id,
        source_entity_id=candidate.source_entity_id,
        target_entity_id=candidate.target_entity_id,
        relationship_type=candidate.relationship_type,
        confidence=candidate.confidence,
        evidence_count=candidate.evidence_count,
        rationale=candidate.rationale,
        resolution_source="inferred",
        details=dict(candidate.details),
    )


def _apply_explicit_assertions(
    *,
    resolved: Sequence[ResolvedRelationship],
    assertions: dict[tuple[str, str, str], RelationshipAssertion],
) -> list[ResolvedRelationship]:
    """Apply explicit assertion overrides on top of inferred resolved relationships."""

    updated = list(resolved)
    existing_keys = {
        (item.source_entity_id or "", item.target_entity_id or "", item.relationship_type)
        for item in updated
    }
    for key, assertion in sorted(assertions.items()):
        if key in existing_keys:
            updated = [
                item
                if (
                    item.source_entity_id or "",
                    item.target_entity_id or "",
                    item.relationship_type,
                )
                != key
                else ResolvedRelationship(
                    source_repo_id=item.source_repo_id or assertion.source_repo_id,
                    target_repo_id=item.target_repo_id or assertion.target_repo_id,
                    source_entity_id=key[0],
                    target_entity_id=key[1],
                    relationship_type=assertion.relationship_type,
                    confidence=1.0,
                    evidence_count=item.evidence_count,
                    rationale=assertion.reason,
                    resolution_source="assertion",
                    details={**item.details, "actor": assertion.actor},
                )
                for item in updated
            ]
            continue
        updated.append(
            ResolvedRelationship(
                source_repo_id=assertion.source_repo_id,
                target_repo_id=assertion.target_repo_id,
                source_entity_id=key[0],
                target_entity_id=key[1],
                relationship_type=assertion.relationship_type,
                confidence=1.0,
                evidence_count=0,
                rationale=assertion.reason,
                resolution_source="assertion",
                details={"actor": assertion.actor},
            )
        )
    return updated


__all__ = ["resolve_entity_relationships"]
