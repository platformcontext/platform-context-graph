"""AWS CI/CD resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_codebuild_project(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_codebuild_project resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CODEBUILD_PROJECT",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.88,
            rationale="Terraform CodeBuild project provisions CI/CD for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "project_name": name,
            },
        )
    ]


def _extract_codepipeline(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_codepipeline resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CODEPIPELINE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.90,
            rationale="Terraform CodePipeline provisions a deployment pipeline for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "pipeline_name": name,
            },
        )
    ]


def _extract_codedeploy_app(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_codedeploy_app resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CODEDEPLOY_APP",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.90,
            rationale="Terraform CodeDeploy provisions deployment automation for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "app_name": name,
            },
        )
    ]


register_resource_extractor(["aws_codebuild_project"], _extract_codebuild_project)
register_resource_extractor(["aws_codepipeline"], _extract_codepipeline)
register_resource_extractor(["aws_codedeploy_app"], _extract_codedeploy_app)
