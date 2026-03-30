"""GCP networking resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    register_resource_extractor,
)


def _extract_dns_record_set(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from google_dns_record_set resources."""
    name = first_quoted_value(body, "name")
    if not name:
        return []
    candidate = name.rstrip(".").split(".")[0] if "." in name else name
    if not candidate or len(candidate) < 3:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_GCP_DNS_RECORD",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform GCP DNS record provisions DNS for the target repository",
            candidate_name=candidate,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "dns_name": name,
            },
        )
    ]


register_resource_extractor(["google_dns_record_set"], _extract_dns_record_set)
