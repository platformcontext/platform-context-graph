"""Terraform evidence extraction orchestrator.

Imports all provider modules to trigger resource extractor registration,
then provides the main evidence discovery entry point that delegates to
registered per-resource-type extractors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    append_relationship_evidence,
)
from ..models import RelationshipEvidenceFact, RepositoryCheckout
from ._base import (
    ExtractionContext,
    RESOURCE_BLOCK_RE,
    get_extractors_for_type,
)

# Import provider modules to trigger extractor registration.
from . import aws  # noqa: F401
from . import cloudflare  # noqa: F401
from . import gcp  # noqa: F401
from . import azure  # noqa: F401


def discover_terraform_resource_evidence(
    *,
    checkout: RepositoryCheckout,
    catalog: Sequence[CatalogEntry],
    content: str,
    file_path: Path,
    local_values: dict[str, str],
    seen: set[tuple[str, str, str, str]],
) -> list[RelationshipEvidenceFact]:
    """Extract relationship evidence from Terraform resource blocks.

    Scans the file content for all ``resource`` blocks, delegates to
    registered provider extractors, and translates the results into
    ``RelationshipEvidenceFact`` objects.

    Args:
        checkout: Repository checkout record.
        catalog: Alias catalog for repository matching.
        content: Full Terraform file content.
        file_path: Source file path (or synthetic path from content store).
        local_values: Resolved ``locals`` assignments from the file.
        seen: Deduplication set for evidence facts.

    Returns:
        List of relationship evidence facts extracted from resource blocks.
    """

    ctx = ExtractionContext(
        checkout=checkout,
        catalog=catalog,
        content=content,
        file_path=file_path,
        local_values=local_values,
    )

    evidence: list[RelationshipEvidenceFact] = []

    for match in RESOURCE_BLOCK_RE.finditer(content):
        resource_type = match.group("resource_type").strip().lower()
        resource_name = match.group("resource_name")
        body = match.group("body")

        extractors = get_extractors_for_type(resource_type)
        if not extractors:
            continue

        for extractor in extractors:
            relationships = extractor(ctx, resource_type, resource_name, body)
            for rel in relationships:
                if rel.candidate_name:
                    append_evidence_for_candidate(
                        evidence=evidence,
                        seen=seen,
                        catalog=catalog,
                        source_repo_id=(rel.source_repo_id or checkout.logical_repo_id),
                        candidate=rel.candidate_name,
                        evidence_kind=rel.evidence_kind,
                        relationship_type=rel.relationship_type,
                        confidence=rel.confidence,
                        rationale=rel.rationale,
                        path=file_path,
                        extractor="terraform",
                        extra_details=rel.extra_details or None,
                    )
                elif rel.source_entity_id or rel.target_entity_id:
                    append_relationship_evidence(
                        evidence=evidence,
                        seen=seen,
                        source_repo_id=(rel.source_repo_id or checkout.logical_repo_id),
                        target_repo_id=rel.target_repo_id,
                        source_entity_id=rel.source_entity_id,
                        target_entity_id=rel.target_entity_id,
                        evidence_kind=rel.evidence_kind,
                        relationship_type=rel.relationship_type,
                        confidence=rel.confidence,
                        rationale=rel.rationale,
                        path=file_path,
                        extractor="terraform",
                        extra_details=rel.extra_details or None,
                    )

    return evidence


__all__ = ["discover_terraform_resource_evidence"]
