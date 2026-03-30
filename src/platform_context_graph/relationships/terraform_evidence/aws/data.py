"""AWS data store resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_rds_cluster(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_rds_cluster resources."""

    identifier = first_non_empty(
        first_quoted_value(body, "cluster_identifier"),
        resource_name,
    )
    if not identifier:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_RDS_CLUSTER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.80,
            rationale="Terraform RDS cluster provisions a database for the target repository",
            candidate_name=identifier,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "cluster_identifier": identifier,
                "engine": first_quoted_value(body, "engine"),
            },
        )
    ]


def _extract_dynamodb_table(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_dynamodb_table resources."""

    name = first_non_empty(
        first_quoted_value(body, "name"),
        resource_name,
    )
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_DYNAMODB_TABLE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform DynamoDB table provisions a data store for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "table_name": name,
            },
        )
    ]


def _extract_elasticache_cluster(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_elasticache_cluster resources."""

    cluster_id = first_non_empty(
        first_quoted_value(body, "cluster_id"),
        first_quoted_value(body, "replication_group_id"),
        resource_name,
    )
    if not cluster_id:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_ELASTICACHE_CLUSTER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.80,
            rationale="Terraform ElastiCache cluster provisions a cache for the target repository",
            candidate_name=cluster_id,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "cluster_id": cluster_id,
                "engine": first_quoted_value(body, "engine"),
            },
        )
    ]


def _extract_search_domain(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from Elasticsearch/OpenSearch domain resources."""

    domain_name = first_non_empty(
        first_quoted_value(body, "domain_name"),
        resource_name,
    )
    if not domain_name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_SEARCH_DOMAIN",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform search domain provisions a search engine for the target repository",
            candidate_name=domain_name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "domain_name": domain_name,
            },
        )
    ]


def _extract_docdb_cluster(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_docdb_cluster resources."""

    identifier = first_non_empty(
        first_quoted_value(body, "cluster_identifier"),
        resource_name,
    )
    if not identifier:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_DOCDB_CLUSTER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.80,
            rationale="Terraform DocumentDB cluster provisions a document store for the target repository",
            candidate_name=identifier,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "cluster_identifier": identifier,
            },
        )
    ]


def _extract_redshift_cluster(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_redshift_cluster resources."""

    identifier = first_non_empty(
        first_quoted_value(body, "cluster_identifier"),
        resource_name,
    )
    if not identifier:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_REDSHIFT_CLUSTER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.80,
            rationale="Terraform Redshift cluster provisions a data warehouse for the target repository",
            candidate_name=identifier,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "cluster_identifier": identifier,
            },
        )
    ]


# Register data store extractors.
register_resource_extractor(
    ["aws_rds_cluster", "aws_db_instance"], _extract_rds_cluster
)
register_resource_extractor(["aws_dynamodb_table"], _extract_dynamodb_table)
register_resource_extractor(
    ["aws_elasticache_cluster", "aws_elasticache_replication_group"],
    _extract_elasticache_cluster,
)
register_resource_extractor(
    ["aws_elasticsearch_domain", "aws_opensearch_domain"], _extract_search_domain
)
register_resource_extractor(["aws_docdb_cluster"], _extract_docdb_cluster)
register_resource_extractor(["aws_redshift_cluster"], _extract_redshift_cluster)
