"""Evidence-backed repository relationship resolution helpers."""

from .models import (
    MetadataAssertion,
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
    ResolutionGeneration,
)
from .postgres import PostgresRelationshipStore
from .resolver import (
    REPOSITORY_DEPENDENCY_SCOPE,
    resolve_repository_relationships,
    resolve_repository_relationships_for_committed_repositories,
)
from .state import get_relationship_store, reset_relationship_store_for_tests

__all__ = [
    "MetadataAssertion",
    "PostgresRelationshipStore",
    "REPOSITORY_DEPENDENCY_SCOPE",
    "RelationshipAssertion",
    "RelationshipCandidate",
    "RelationshipEvidenceFact",
    "RepositoryCheckout",
    "ResolvedRelationship",
    "ResolutionGeneration",
    "get_relationship_store",
    "reset_relationship_store_for_tests",
    "resolve_repository_relationships",
    "resolve_repository_relationships_for_committed_repositories",
]
