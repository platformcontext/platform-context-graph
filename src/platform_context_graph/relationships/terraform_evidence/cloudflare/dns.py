"""Cloudflare DNS resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    register_resource_extractor,
)


def _extract_dns_record(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from cloudflare_dns_record and cloudflare_record resources."""
    name = first_quoted_value(body, "name")
    if not name:
        return []
    candidate = name.split(".")[0] if "." in name else name
    if not candidate or len(candidate) < 3:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUDFLARE_DNS_RECORD",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform Cloudflare DNS record provisions DNS for the target repository",
            candidate_name=candidate,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "dns_name": name,
                "record_type": first_quoted_value(body, "type"),
            },
        )
    ]


register_resource_extractor(
    ["cloudflare_dns_record", "cloudflare_record"], _extract_dns_record
)
