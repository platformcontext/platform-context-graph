"""AWS messaging resource evidence extractors."""

from __future__ import annotations

from .._base import (
    ExtractionContext,
    ResourceRelationship,
    first_quoted_value,
    first_non_empty,
    register_resource_extractor,
)


def _extract_sqs_queue(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_sqs_queue resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_SQS_QUEUE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.84,
            rationale="Terraform SQS queue provisions messaging for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "queue_name": name,
            },
        )
    ]


def _extract_sns_topic(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_sns_topic resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_SNS_TOPIC",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.82,
            rationale="Terraform SNS topic provisions notifications for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "topic_name": name,
            },
        )
    ]


def _extract_mq_broker(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_mq_broker resources."""
    name = first_non_empty(first_quoted_value(body, "broker_name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_MQ_BROKER",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.85,
            rationale="Terraform MQ broker provisions messaging for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "broker_name": name,
            },
        )
    ]


def _extract_sfn_state_machine(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_sfn_state_machine resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_SFN_STATE_MACHINE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.88,
            rationale="Terraform Step Functions state machine provisions a workflow for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "state_machine_name": name,
            },
        )
    ]


def _extract_eventbridge_rule(
    ctx: ExtractionContext,
    resource_type: str,
    resource_name: str,
    body: str,
) -> list[ResourceRelationship]:
    """Extract relationships from aws_cloudwatch_event_rule resources."""
    name = first_non_empty(first_quoted_value(body, "name"), resource_name)
    if not name:
        return []
    return [
        ResourceRelationship(
            evidence_kind="TERRAFORM_EVENTBRIDGE_RULE",
            relationship_type="PROVISIONS_DEPENDENCY_FOR",
            confidence=0.80,
            rationale="Terraform EventBridge rule provisions event routing for the target repository",
            candidate_name=name,
            extra_details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "rule_name": name,
            },
        )
    ]


register_resource_extractor(["aws_sqs_queue"], _extract_sqs_queue)
register_resource_extractor(["aws_sns_topic"], _extract_sns_topic)
register_resource_extractor(["aws_mq_broker"], _extract_mq_broker)
register_resource_extractor(["aws_sfn_state_machine"], _extract_sfn_state_machine)
register_resource_extractor(["aws_cloudwatch_event_rule"], _extract_eventbridge_rule)
