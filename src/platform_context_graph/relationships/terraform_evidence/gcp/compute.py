"""GCP compute resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_cloud_run_service(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from google_cloud_run_service resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUD_RUN_SERVICE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.92,
            rationale="Terraform Cloud Run service provisions serverless compute for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "service_name": name,
                "location": first_quoted_value(body, "location"),
            },
        )
    ]


def _extract_gke_cluster(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from google_container_cluster resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_GKE_CLUSTER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.85,
            rationale="Terraform GKE cluster provisions a Kubernetes platform",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "cluster_name": name,
                "location": first_quoted_value(body, "location"),
            },
        )
    ]


register_resource_extractor(
    ["google_cloud_run_service", "google_cloud_run_v2_service"],
    _extract_cloud_run_service,
)
register_resource_extractor(["google_container_cluster"], _extract_gke_cluster)
