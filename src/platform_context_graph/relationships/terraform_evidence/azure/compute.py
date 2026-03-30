"""Azure compute resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_aks_cluster(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from azurerm_kubernetes_cluster resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_AKS_CLUSTER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.85,
            rationale="Terraform AKS cluster provisions a Kubernetes platform",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "cluster_name": name,
            },
        )
    ]


def _extract_container_app(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from azurerm_container_app resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CONTAINER_APP",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.90,
            rationale="Terraform Azure Container App provisions serverless compute for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "app_name": name,
            },
        )
    ]


register_resource_extractor(["azurerm_kubernetes_cluster"], _extract_aks_cluster)
register_resource_extractor(["azurerm_container_app"], _extract_container_app)
