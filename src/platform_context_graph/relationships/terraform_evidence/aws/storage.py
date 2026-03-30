"""AWS storage resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_s3_bucket(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_s3_bucket resources."""
    bucket = first_non_empty(first_quoted_value(body, "bucket"), resource_name)
    if not bucket:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_S3_BUCKET",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.78,
            rationale="Terraform S3 bucket provisions object storage for the target repository",
            candidate_name=bucket,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "bucket": bucket,
            },
        )
    ]


def _extract_ecr_repository(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_ecr_repository resources.

    ECR repository names frequently match the source code repository name
    (e.g., ``api-node-boats`` ECR repo for the ``api-node-boats`` code repo).
    """
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_ECR_REPOSITORY",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.94,
            rationale="Terraform ECR repository provisions a container registry for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "repository_name": name,
            },
        )
    ]


def _extract_efs_file_system(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_efs_file_system resources."""
    name = first_non_empty(
        first_quoted_value(body, "creation_token"),
        resource_name,
    )
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_EFS_FILE_SYSTEM",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.78,
            rationale="Terraform EFS file system provisions shared storage for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "file_system_name": name,
            },
        )
    ]


register_resource_extractor(["aws_s3_bucket"], _extract_s3_bucket)
register_resource_extractor(["aws_ecr_repository"], _extract_ecr_repository)
register_resource_extractor(["aws_efs_file_system"], _extract_efs_file_system)
