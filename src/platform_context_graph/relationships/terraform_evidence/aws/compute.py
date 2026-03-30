"""AWS compute resource evidence extractors (ECS, EKS, Lambda, Batch, EC2)."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
    resolve_assignment_value,
)


def _extract_ecs_service(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_ecs_service resources."""

    relationships: list[ResourceRelationship] = []
    service_name = first_non_empty(
        first_quoted_value(body, "name"),
        resource_name,
    )
    if service_name:
        relationships.append(
            ResourceRelationship(
                evidence_kind="TERRAFORM_ECS_SERVICE",
                relationship_type="PROVISIONS_DEPENDENCY_FOR",
                confidence=0.93,
                rationale="Terraform ECS service provisions infrastructure for the target repository",
                candidate_name=service_name,
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "service_name": service_name,
                },
            )
        )
    return relationships


def _extract_ecs_task_definition(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_ecs_task_definition resources."""

    relationships: list[ResourceRelationship] = []
    family = first_non_empty(
        first_quoted_value(body, "family"),
        resource_name,
    )
    if family:
        relationships.append(
            ResourceRelationship(
                evidence_kind="TERRAFORM_ECS_TASK_DEFINITION",
                relationship_type="PROVISIONS_DEPENDENCY_FOR",
                confidence=0.91,
                rationale="Terraform ECS task definition provisions infrastructure for the target repository",
                candidate_name=family,
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "family": family,
                },
            )
        )
    return relationships


def _extract_lambda_function(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_lambda_function resources."""

    relationships: list[ResourceRelationship] = []
    function_name = first_non_empty(
        first_quoted_value(body, "function_name"),
        resource_name,
    )
    handler = first_quoted_value(body, "handler")
    runtime = first_quoted_value(body, "runtime")
    s3_key = first_quoted_value(body, "s3_key")

    if function_name:
        relationships.append(
            ResourceRelationship(
                evidence_kind="TERRAFORM_LAMBDA_FUNCTION",
                relationship_type="PROVISIONS_DEPENDENCY_FOR",
                confidence=0.93,
                rationale="Terraform Lambda function provisions infrastructure for the target repository",
                candidate_name=function_name,
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "function_name": function_name,
                    "handler": handler,
                    "runtime": runtime,
                    "s3_key": s3_key,
                },
            )
        )
    return relationships


def _extract_batch_job_definition(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_batch_job_definition resources."""

    relationships: list[ResourceRelationship] = []
    name = first_non_empty(
        first_quoted_value(body, "name"),
        resource_name,
    )
    if name:
        relationships.append(
            ResourceRelationship(
                evidence_kind="TERRAFORM_BATCH_JOB_DEFINITION",
                relationship_type="PROVISIONS_DEPENDENCY_FOR",
                confidence=0.90,
                rationale="Terraform Batch job definition provisions infrastructure for the target repository",
                candidate_name=name,
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "job_name": name,
                },
            )
        )
    return relationships


def _extract_batch_compute_environment(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_batch_compute_environment resources."""

    relationships: list[ResourceRelationship] = []
    name = first_non_empty(
        first_quoted_value(body, "compute_environment_name"),
        resource_name,
    )
    if name:
        relationships.append(
            ResourceRelationship(
                evidence_kind="TERRAFORM_BATCH_COMPUTE_ENVIRONMENT",
                relationship_type="PROVISIONS_DEPENDENCY_FOR",
                confidence=0.88,
                rationale="Terraform Batch compute environment provisions infrastructure for the target repository",
                candidate_name=name,
                extra_details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "compute_environment_name": name,
                },
            )
        )
    return relationships


# Register all compute extractors.
register_resource_extractor(["aws_ecs_service"], _extract_ecs_service)
register_resource_extractor(["aws_ecs_task_definition"], _extract_ecs_task_definition)
register_resource_extractor(["aws_lambda_function"], _extract_lambda_function)
register_resource_extractor(["aws_batch_job_definition"], _extract_batch_job_definition)
register_resource_extractor(
    ["aws_batch_compute_environment"], _extract_batch_compute_environment
)
