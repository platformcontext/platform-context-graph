"""Shared domain models for entities, requests, and responses."""

from .entities import (
    EntityRef,
    EntityType,
    WorkloadKind,
    normalize_entity_type,
    normalize_workload_kind,
)
from .requests import ResolveEntityRequest
from .responses import (
    AliasMetadata,
    EvidenceItem,
    InferenceMetadata,
    ProblemDetails,
    RepoAccess,
    ResolveEntityMatch,
    ResponseEnvelope,
)

__all__ = [
    "AliasMetadata",
    "EntityRef",
    "EntityType",
    "EvidenceItem",
    "InferenceMetadata",
    "ProblemDetails",
    "RepoAccess",
    "ResolveEntityMatch",
    "ResolveEntityRequest",
    "ResponseEnvelope",
    "WorkloadKind",
    "normalize_entity_type",
    "normalize_workload_kind",
]
