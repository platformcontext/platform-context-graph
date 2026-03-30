"""AWS networking resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_route53_record(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_route53_record resources."""

    name = first_quoted_value(body, "name")
    if not name:
        return []
    # DNS records often encode the service name in the hostname
    # e.g., "api-node-boats.qa.bgrp.io" → candidate "api-node-boats"
    candidate = name.split(".")[0] if "." in name else name
    if not candidate or len(candidate) < 3:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_ROUTE53_RECORD",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform Route53 record provisions DNS for the target repository",
            candidate_name=candidate,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "dns_name": name,
            },
        )
    ]


def _extract_lb(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_lb and aws_alb resources."""

    name = first_non_empty(
        first_quoted_value(body, "name"),
        resource_name,
    )
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_LOAD_BALANCER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.85,
            rationale="Terraform load balancer provisions networking for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "lb_name": name,
            },
        )
    ]


def _extract_cloudfront_distribution(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_cloudfront_distribution resources."""

    comment = first_quoted_value(body, "comment")
    candidate = comment if comment else resource_name
    if not candidate:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_CLOUDFRONT_DISTRIBUTION",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.84,
            rationale="Terraform CloudFront distribution provisions CDN for the target repository",
            candidate_name=candidate,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "comment": comment,
            },
        )
    ]


def _extract_api_gateway(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from API Gateway resources."""

    name = first_non_empty(
        first_quoted_value(body, "name"),
        resource_name,
    )
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_API_GATEWAY",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.90,
            rationale="Terraform API Gateway provisions an API endpoint for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "api_name": name,
            },
        )
    ]


def _extract_service_discovery(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_service_discovery_service resources."""

    name = first_non_empty(
        first_quoted_value(body, "name"),
        resource_name,
    )
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_SERVICE_DISCOVERY",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.92,
            rationale="Terraform service discovery registers the target repository as a service",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "service_name": name,
            },
        )
    ]


# Register networking extractors.
register_resource_extractor(["aws_route53_record"], _extract_route53_record)
register_resource_extractor(["aws_lb", "aws_alb"], _extract_lb)
register_resource_extractor(
    ["aws_cloudfront_distribution"], _extract_cloudfront_distribution
)
register_resource_extractor(
    ["aws_api_gateway_rest_api", "aws_apigatewayv2_api"], _extract_api_gateway
)
register_resource_extractor(
    ["aws_service_discovery_service"], _extract_service_discovery
)
