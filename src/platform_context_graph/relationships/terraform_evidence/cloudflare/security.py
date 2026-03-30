"""Cloudflare security resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    register_resource_extractor,
)


def _extract_waf_ruleset(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from cloudflare_ruleset resources."""
    name = first_quoted_value(body, "name")
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUDFLARE_RULESET",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.78,
            rationale="Terraform Cloudflare WAF ruleset provisions security for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "ruleset_name": name,
            },
        )
    ]


register_resource_extractor(["cloudflare_ruleset"], _extract_waf_ruleset)
