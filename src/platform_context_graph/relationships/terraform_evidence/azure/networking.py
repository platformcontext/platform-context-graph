"""Azure networking resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_dns_record(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from Azure DNS record resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name or len(name) < 3:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_AZURE_DNS_RECORD",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform Azure DNS record provisions DNS for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "dns_name": name,
            },
        )
    ]


def _extract_frontdoor(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from azurerm_frontdoor resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_AZURE_FRONTDOOR",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.85,
            rationale="Terraform Azure Front Door provisions CDN and routing for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "frontdoor_name": name,
            },
        )
    ]


register_resource_extractor(
    ["azurerm_dns_a_record", "azurerm_dns_cname_record"], _extract_dns_record
)
register_resource_extractor(
    ["azurerm_frontdoor", "azurerm_cdn_frontdoor_route"], _extract_frontdoor
)
