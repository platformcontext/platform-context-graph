"""Shared domain models for entities, requests, and responses."""

from .entities import (
    EntityRef,
    EntityType,
    WorkloadKind,
    normalize_entity_type,
    normalize_workload_kind,
)
from .requests import ResolveEntityRequest
from .investigation_responses import InvestigationResponse
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
    "InvestigationResponse",
    "ProblemDetails",
    "RepoAccess",
    "ResolveEntityMatch",
    "ResolveEntityRequest",
    "ResponseEnvelope",
    "WorkloadKind",
    "normalize_entity_type",
    "normalize_workload_kind",
]
