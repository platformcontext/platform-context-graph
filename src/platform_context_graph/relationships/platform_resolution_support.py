"""Support helpers for mixed-entity platform relationship resolution."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .models import RelationshipCandidate, ResolvedRelationship

GENERIC_RELATIONSHIP_TYPE = "DEPENDS_ON"
DIRECT_DERIVED_GENERIC_DIRECTION = {
    "DEPLOYS_FROM": "forward",
    "DISCOVERS_CONFIG_IN": "forward",
    "PROVISIONS_DEPENDENCY_FOR": "reverse",
    "RUNS_ON": "forward",
}
PLATFORM_PROVISION_RELATIONSHIP_TYPE = "PROVISIONS_PLATFORM"
PLATFORM_RUNTIME_RELATIONSHIP_TYPE = "RUNS_ON"


def entity_identity(*, entity_id: str | None, repository_id: str | None) -> str | None:
    """Return the canonical entity id for one relationship endpoint."""

    return entity_id or repository_id


def preferred_repository_id(
    *,
    entity_id: str | None,
    repository_ids: Sequence[str | None],
) -> str | None:
    """Choose the best repository id for one grouped entity endpoint."""

    if entity_id and is_repository_entity(entity_id):
        return entity_id
    for repository_id in repository_ids:
        if repository_id:
            return repository_id
    return None


def is_repository_entity(entity_id: str | None) -> bool:
    """Return whether the canonical entity id refers to a repository."""

    return bool(entity_id) and entity_id.startswith("repository:")


def suppress_generic_relationship_candidates(
    candidates: Sequence[RelationshipCandidate],
) -> list[RelationshipCandidate]:
    """Drop inferred generic candidates when a typed edge exists for the same pair."""

    typed_pairs = {
        derived_pair
        for candidate in candidates
        if candidate.relationship_type != GENERIC_RELATIONSHIP_TYPE
        for derived_pair in iter_suppressed_generic_pairs_for_relationship(
            source_entity_id=candidate.source_entity_id,
            target_entity_id=candidate.target_entity_id,
            relationship_type=candidate.relationship_type,
        )
    }
    if not typed_pairs:
        return list(candidates)
    return [
        candidate
        for candidate in candidates
        if candidate.relationship_type != GENERIC_RELATIONSHIP_TYPE
        or (candidate.source_entity_id, candidate.target_entity_id) not in typed_pairs
    ]


def derive_direct_generic_relationships(
    *,
    resolved: Sequence[ResolvedRelationship],
    rejections: set[tuple[str, str, str]],
) -> list[ResolvedRelationship]:
    """Derive repo-to-repo compatibility edges from typed canonical facts."""

    typed_groups: dict[tuple[str, str], list[ResolvedRelationship]] = defaultdict(list)
    existing_generic_pairs = {
        (item.source_entity_id or "", item.target_entity_id or "")
        for item in resolved
        if item.relationship_type == GENERIC_RELATIONSHIP_TYPE
    }
    for item in resolved:
        if item.relationship_type == GENERIC_RELATIONSHIP_TYPE:
            continue
        for pair in iter_repo_compat_pairs_for_relationship(
            source_entity_id=item.source_entity_id,
            target_entity_id=item.target_entity_id,
            relationship_type=item.relationship_type,
        ):
            typed_groups[pair].append(item)

    derived: list[ResolvedRelationship] = []
    for (source_entity_id, target_entity_id), items in sorted(typed_groups.items()):
        generic_key = (source_entity_id, target_entity_id, GENERIC_RELATIONSHIP_TYPE)
        if (
            generic_key in rejections
            or (source_entity_id, target_entity_id) in existing_generic_pairs
        ):
            continue
        relationship_types = sorted({item.relationship_type for item in items})
        derived.append(
            ResolvedRelationship(
                source_repo_id=preferred_repository_id(
                    entity_id=source_entity_id,
                    repository_ids=[item.source_repo_id for item in items],
                ),
                target_repo_id=preferred_repository_id(
                    entity_id=target_entity_id,
                    repository_ids=[item.target_repo_id for item in items],
                ),
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=GENERIC_RELATIONSHIP_TYPE,
                confidence=max(item.confidence for item in items),
                evidence_count=sum(item.evidence_count for item in items),
                rationale=(
                    "Derived compatibility dependency from typed relationships: "
                    + ", ".join(relationship_types)
                ),
                resolution_source="derived",
                details={
                    "derived_from_relationship_types": relationship_types,
                    "derived_from_resolution_sources": sorted(
                        {item.resolution_source for item in items}
                    ),
                },
            )
        )
    return derived


def derive_platform_chain_dependencies(
    *,
    resolved: Sequence[ResolvedRelationship],
    rejections: set[tuple[str, str, str]],
) -> list[ResolvedRelationship]:
    """Derive repo-level compatibility edges from RUNS_ON and PROVISIONS_PLATFORM."""

    provisioners_by_platform: dict[str, list[ResolvedRelationship]] = defaultdict(list)
    runners_by_platform: dict[str, list[ResolvedRelationship]] = defaultdict(list)
    existing_generic_pairs = {
        (item.source_entity_id or "", item.target_entity_id or "")
        for item in resolved
        if item.relationship_type == GENERIC_RELATIONSHIP_TYPE
    }

    for item in resolved:
        if (
            item.relationship_type == PLATFORM_PROVISION_RELATIONSHIP_TYPE
            and item.target_entity_id is not None
        ):
            provisioners_by_platform[item.target_entity_id].append(item)
        elif (
            item.relationship_type == PLATFORM_RUNTIME_RELATIONSHIP_TYPE
            and item.target_entity_id is not None
        ):
            runners_by_platform[item.target_entity_id].append(item)

    derived: list[ResolvedRelationship] = []
    for platform_id, runners in sorted(runners_by_platform.items()):
        provisioners = provisioners_by_platform.get(platform_id, [])
        if not provisioners:
            continue
        for runner in runners:
            source_entity_id = preferred_repository_id(
                entity_id=runner.source_entity_id,
                repository_ids=[runner.source_repo_id],
            )
            if source_entity_id is None:
                continue
            for provisioner in provisioners:
                target_entity_id = preferred_repository_id(
                    entity_id=provisioner.source_entity_id,
                    repository_ids=[provisioner.source_repo_id],
                )
                if target_entity_id is None or source_entity_id == target_entity_id:
                    continue
                generic_key = (
                    source_entity_id,
                    target_entity_id,
                    GENERIC_RELATIONSHIP_TYPE,
                )
                if (
                    generic_key in rejections
                    or (source_entity_id, target_entity_id) in existing_generic_pairs
                ):
                    continue
                derived.append(
                    ResolvedRelationship(
                        source_repo_id=source_entity_id,
                        target_repo_id=target_entity_id,
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        relationship_type=GENERIC_RELATIONSHIP_TYPE,
                        confidence=min(runner.confidence, provisioner.confidence),
                        evidence_count=runner.evidence_count
                        + provisioner.evidence_count,
                        rationale=(
                            "Derived compatibility dependency from platform chain: "
                            f"{runner.relationship_type} + {provisioner.relationship_type}"
                        ),
                        resolution_source="derived",
                        details={
                            "derived_from_relationship_types": sorted(
                                {
                                    runner.relationship_type,
                                    provisioner.relationship_type,
                                }
                            ),
                            "platform_entity_id": platform_id,
                            "derived_from_resolution_sources": sorted(
                                {
                                    runner.resolution_source,
                                    provisioner.resolution_source,
                                }
                            ),
                        },
                    )
                )
                existing_generic_pairs.add((source_entity_id, target_entity_id))
    return derived


def dedupe_resolved_relationships(
    resolved: Sequence[ResolvedRelationship],
) -> list[ResolvedRelationship]:
    """Collapse duplicate resolved rows while preserving provenance."""

    deduped: dict[tuple[str | None, str | None, str], ResolvedRelationship] = {}
    for item in resolved:
        key = (item.source_entity_id, item.target_entity_id, item.relationship_type)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = item
            continue
        deduped[key] = ResolvedRelationship(
            source_repo_id=existing.source_repo_id or item.source_repo_id,
            target_repo_id=existing.target_repo_id or item.target_repo_id,
            source_entity_id=existing.source_entity_id or item.source_entity_id,
            target_entity_id=existing.target_entity_id or item.target_entity_id,
            relationship_type=existing.relationship_type,
            confidence=max(existing.confidence, item.confidence),
            evidence_count=existing.evidence_count + item.evidence_count,
            rationale=_merge_text(existing.rationale, item.rationale),
            resolution_source=_merge_resolution_source(
                existing.resolution_source,
                item.resolution_source,
            ),
            details=_merge_details(existing.details, item.details),
        )
    return list(deduped.values())


def iter_suppressed_generic_pairs_for_relationship(
    *,
    source_entity_id: str | None,
    target_entity_id: str | None,
    relationship_type: str,
) -> tuple[tuple[str, str], ...]:
    """Return the entity pairs whose generic candidates should be suppressed."""

    if source_entity_id is None or target_entity_id is None:
        return ()
    direction = DIRECT_DERIVED_GENERIC_DIRECTION.get(relationship_type)
    if direction == "reverse":
        return ((target_entity_id, source_entity_id),)
    if direction == "forward":
        return ((source_entity_id, target_entity_id),)
    return ()


def iter_repo_compat_pairs_for_relationship(
    *,
    source_entity_id: str | None,
    target_entity_id: str | None,
    relationship_type: str,
) -> tuple[tuple[str, str], ...]:
    """Return the repo-to-repo compatibility pair implied by one typed edge."""

    for source_id, target_id in iter_suppressed_generic_pairs_for_relationship(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
    ):
        if is_repository_entity(source_id) and is_repository_entity(target_id):
            return ((source_id, target_id),)
    return ()


def _merge_text(left: str, right: str) -> str:
    """Merge two rationale strings while preserving stable order."""

    values = [value for value in (left, right) if value]
    return "; ".join(dict.fromkeys(values))


def _merge_resolution_source(left: str, right: str) -> str:
    """Merge two resolution sources conservatively."""

    if left == right:
        return left
    if "assertion" in {left, right}:
        return "assertion"
    return "derived"


def _merge_details(
    left: dict[str, object],
    right: dict[str, object],
) -> dict[str, object]:
    """Merge two details dictionaries without discarding list provenance."""

    merged = dict(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = value
            continue
        existing = merged[key]
        if isinstance(existing, list) and isinstance(value, list):
            merged[key] = list(dict.fromkeys([*existing, *value]))
        elif isinstance(existing, dict) and isinstance(value, dict):
            nested = dict(existing)
            nested.update(value)
            merged[key] = nested
        elif existing == value:
            merged[key] = existing
        else:
            merged[key] = [existing, value]
    return merged


__all__ = [
    "GENERIC_RELATIONSHIP_TYPE",
    "derive_direct_generic_relationships",
    "derive_platform_chain_dependencies",
    "dedupe_resolved_relationships",
    "entity_identity",
    "preferred_repository_id",
    "suppress_generic_relationship_candidates",
]
