"""Dataclasses for evidence-backed relationship resolution and canonical entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .entities import (
    CanonicalEntity,
    Platform,
    PlatformEntity,
    Repository,
    RepositoryEntity,
    WorkloadSubject,
    WorkloadSubjectEntity,
    canonical_platform_id,
    canonical_workload_subject_id,
)  # noqa: F401


@dataclass(slots=True)
class RepositoryCheckout:
    """One observed checkout for a logical repository."""

    checkout_id: str
    logical_repo_id: str
    repo_name: str
    repo_slug: str | None = None
    remote_url: str | None = None
    checkout_path: str | None = None


@dataclass(slots=True)
class RelationshipEvidenceFact:
    """One raw observed fact supporting a relationship candidate."""

    evidence_kind: str
    relationship_type: str
    source_repo_id: str
    target_repo_id: str
    confidence: float
    rationale: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RelationshipAssertion:
    """One explicit human or control-plane assertion about a relationship."""

    source_repo_id: str
    target_repo_id: str
    relationship_type: str
    decision: str
    reason: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    actor: str = "system"


@dataclass(slots=True)
class MetadataAssertion:
    """One explicit metadata assertion for a repository or related subject."""

    subject_type: str
    subject_id: str
    key: str
    value: str
    actor: str = "system"


@dataclass(slots=True)
class RelationshipCandidate:
    """One machine-generated relationship candidate."""

    source_repo_id: str
    target_repo_id: str
    relationship_type: str
    confidence: float
    evidence_count: int
    rationale: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolvedRelationship:
    """One canonical relationship emitted by the resolver."""

    source_repo_id: str
    target_repo_id: str
    relationship_type: str
    confidence: float
    evidence_count: int
    rationale: str
    resolution_source: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolutionGeneration:
    """One persisted resolution generation."""

    generation_id: str
    scope: str
    run_id: str | None
    status: str
