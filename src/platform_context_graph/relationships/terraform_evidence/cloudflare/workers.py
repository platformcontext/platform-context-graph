"""Cloudflare Workers resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_workers_script(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from cloudflare_workers_script resources."""
    name = first_non_empty(
        first_quoted_value(body, "name"),
        first_quoted_value(body, "script_name"),
        resource_name,
    )
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUDFLARE_WORKER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.92,
            rationale="Terraform Cloudflare Worker provisions edge compute for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "worker_name": name,
            },
        )
    ]


def _extract_workers_route(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from cloudflare_workers_route resources."""
    pattern = first_quoted_value(body, "pattern")
    script_name = first_quoted_value(body, "script_name")
    candidate = script_name or resource_name
    if not candidate:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUDFLARE_WORKER_ROUTE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.88,
            rationale="Terraform Cloudflare Workers route provisions edge routing for the target repository",
            candidate_name=candidate,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "pattern": pattern,
                "script_name": script_name,
            },
        )
    ]


def _extract_r2_bucket(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from cloudflare_r2_bucket resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUDFLARE_R2_BUCKET",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.80,
            rationale="Terraform Cloudflare R2 bucket provisions object storage for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "bucket_name": name,
            },
        )
    ]


register_resource_extractor(["cloudflare_workers_script"], _extract_workers_script)
register_resource_extractor(["cloudflare_workers_route"], _extract_workers_route)
register_resource_extractor(["cloudflare_r2_bucket"], _extract_r2_bucket)
