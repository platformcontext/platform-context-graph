"""Terraform provider schema loader and resource classification.

Loads JSON schemas produced by ``terraform providers schema -json`` and provides
utilities for resource type discovery, identity-key inference, and service
category classification.  Used by the generic extractor to auto-register
extractors for resource types not covered by hand-written provider modules.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AWS service-prefix → category mapping
# ---------------------------------------------------------------------------
# Keys are the service portion of the resource type *after* stripping the
# provider prefix (e.g. ``aws_lambda_function`` → ``lambda``).  Longer
# prefixes are tried first so ``cloudwatch_event`` matches before
# ``cloudwatch``.

SERVICE_CATEGORIES: dict[str, str] = {
    # Compute
    "lambda": "compute",
    "ecs": "compute",
    "eks": "compute",
    "batch": "compute",
    "ec2": "compute",
    "lightsail": "compute",
    "autoscaling": "compute",
    "apprunner": "compute",
    # Storage
    "s3": "storage",
    "ecr": "storage",
    "efs": "storage",
    "fsx": "storage",
    "glacier": "storage",
    "backup": "storage",
    # Data
    "rds": "data",
    "db": "data",
    "dynamodb": "data",
    "elasticache": "data",
    "elasticsearch": "data",
    "opensearch": "data",
    "docdb": "data",
    "redshift": "data",
    "neptune": "data",
    "keyspaces": "data",
    "timestream": "data",
    "memorydb": "data",
    "dax": "data",
    # Networking
    "route53": "networking",
    "lb": "networking",
    "alb": "networking",
    "cloudfront": "networking",
    "apigateway": "networking",
    "apigatewayv2": "networking",
    "elb": "networking",
    "vpc": "networking",
    "subnet": "networking",
    "security_group": "networking",
    "nat_gateway": "networking",
    "service_discovery": "networking",
    "appmesh": "networking",
    "globalaccelerator": "networking",
    # Messaging
    "sqs": "messaging",
    "sns": "messaging",
    "mq": "messaging",
    "sfn": "messaging",
    "scheduler": "messaging",
    "kinesis": "messaging",
    "pipes": "messaging",
    "cloudwatch_event": "messaging",
    # Security / IAM
    "iam": "security",
    "kms": "security",
    "secretsmanager": "security",
    "ssm": "security",
    "acm": "security",
    "waf": "security",
    "wafv2": "security",
    "shield": "security",
    "guardduty": "security",
    "inspector": "security",
    "macie": "security",
    "cognito": "security",
    # CI/CD
    "codebuild": "cicd",
    "codepipeline": "cicd",
    "codedeploy": "cicd",
    "codecommit": "cicd",
    "codeartifact": "cicd",
    "codestarconnections": "cicd",
    # Monitoring
    "cloudwatch": "monitoring",
    "cloudtrail": "monitoring",
    "xray": "monitoring",
    "synthetics": "monitoring",
    # Governance
    "config": "governance",
    "organizations": "governance",
    "budgets": "governance",
    # --- GCP (google_ prefix) ---
    "cloud_run": "compute",
    "cloud_run_v2": "compute",
    "container": "compute",
    "compute": "compute",
    "app_engine": "compute",
    "cloud_functions": "compute",
    "cloud_functions2": "compute",
    "storage": "storage",
    "artifact_registry": "storage",
    "sql": "data",
    "spanner": "data",
    "bigtable": "data",
    "firestore": "data",
    "redis": "data",
    "bigquery": "data",
    "datastore": "data",
    "alloydb": "data",
    "dns": "networking",
    "compute_forwarding_rule": "networking",
    "pubsub": "messaging",
    "cloud_tasks": "messaging",
    "cloud_scheduler": "messaging",
    "kms_crypto": "security",
    "secret_manager": "security",
    "logging": "monitoring",
    "monitoring": "monitoring",
    "cloudbuild": "cicd",
    "clouddeploy": "cicd",
    # --- Azure (azurerm_ prefix) ---
    "kubernetes_cluster": "compute",
    "container_app": "compute",
    "container_group": "compute",
    "function_app": "compute",
    "linux_web_app": "compute",
    "windows_web_app": "compute",
    "linux_function_app": "compute",
    "storage_account": "storage",
    "storage_container": "storage",
    "container_registry": "storage",
    "mssql": "data",
    "postgresql": "data",
    "mysql": "data",
    "cosmosdb": "data",
    "redis_cache": "data",
    "dns_a_record": "networking",
    "dns_cname_record": "networking",
    "frontdoor": "networking",
    "cdn_frontdoor": "networking",
    "application_gateway": "networking",
    "servicebus": "messaging",
    "eventhub": "messaging",
    "key_vault": "security",
    "role_assignment": "security",
    "log_analytics": "monitoring",
    "monitor": "monitoring",
    # --- Cloudflare ---
    "workers": "compute",
    "r2": "storage",
    "d1": "data",
    "dns_record": "networking",
    "ruleset": "security",
    "access": "security",
    "tunnel": "networking",
    "page_rule": "networking",
    # --- Alibaba Cloud (alicloud_ prefix) ---
    "instance": "compute",
    "ess": "compute",
    "fc": "compute",
    "edas": "compute",
    "oss": "storage",
    "cr": "storage",
    "nas": "storage",
    "db_instance": "data",
    "kvstore": "data",
    "polardb": "data",
    "adb": "data",
    "lindorm": "data",
    "hbase": "data",
    "mongodb": "data",
    "gpdb": "data",
    "slb": "networking",
    "nlb": "networking",
    "alb_listener": "networking",
    "alidns": "networking",
    "cdn": "networking",
    "dcdn": "networking",
    "mns": "messaging",
    "mns_queue": "messaging",
    "mns_topic": "messaging",
    "event_bridge": "messaging",
    "ram": "security",
    "actiontrail": "monitoring",
    "cms": "monitoring",
    "log": "monitoring",
    # --- Oracle Cloud Infrastructure (oci_ prefix) ---
    "core_instance": "compute",
    "containerengine": "compute",
    "functions": "compute",
    "objectstorage": "storage",
    "artifacts": "storage",
    "database": "data",
    "nosql": "data",
    "mysql_mysql": "data",
    "core_vcn": "networking",
    "core_subnet": "networking",
    "load_balancer": "networking",
    "network_load_balancer": "networking",
    "streaming": "messaging",
    "queue": "messaging",
    "identity": "security",
    "vault": "security",
    "waas": "security",
    # --- Kubernetes (kubernetes_ prefix) ---
    "deployment": "compute",
    "deployment_v1": "compute",
    "daemon_set": "compute",
    "daemon_set_v1": "compute",
    "stateful_set": "compute",
    "stateful_set_v1": "compute",
    "job": "compute",
    "job_v1": "compute",
    "cron_job": "compute",
    "cron_job_v1": "compute",
    "pod": "compute",
    "replication_controller": "compute",
    "persistent_volume": "storage",
    "persistent_volume_claim": "storage",
    "persistent_volume_claim_v1": "storage",
    "config_map": "governance",
    "config_map_v1": "governance",
    "secret": "security",
    "secret_v1": "security",
    "service": "networking",
    "service_v1": "networking",
    "ingress": "networking",
    "ingress_v1": "networking",
    "network_policy": "networking",
    "network_policy_v1": "networking",
    "namespace": "governance",
    "namespace_v1": "governance",
    "service_account": "security",
    "service_account_v1": "security",
    "role": "security",
    "role_binding": "security",
    "cluster_role": "security",
    "cluster_role_binding": "security",
    "horizontal_pod_autoscaler": "compute",
    # --- Helm ---
    "release": "compute",
}

# Well-known attribute names that serve as resource identifiers, ordered by
# preference.  The first match wins.
_IDENTITY_KEY_PATTERNS: tuple[str, ...] = (
    "name",
    "function_name",
    "bucket",
    "family",
    "queue_name",
    "topic_name",
    "cluster_identifier",
    "cluster_id",
    "cluster_name",
    "replication_group_id",
    "domain_name",
    "broker_name",
    "table_name",
    "repository_name",
    "project_name",
    "pipeline_name",
    "app_name",
    "service_name",
    "rule_name",
    "db_name",
    "creation_token",
    "instance_id",
)


@dataclass(frozen=True, slots=True)
class ProviderSchemaInfo:
    """Parsed Terraform provider schema."""

    provider_key: str
    provider_name: str
    format_version: str
    resource_types: dict[str, dict[str, Any]] = field(repr=False)

    @property
    def resource_count(self) -> int:
        """Return the number of resource types in the schema."""
        return len(self.resource_types)


def load_provider_schema(schema_path: Path) -> ProviderSchemaInfo | None:
    """Load a Terraform provider schema from JSON or gzipped JSON.

    Returns ``None`` when the file does not exist or is malformed.
    """

    if not schema_path.exists():
        return None

    try:
        if schema_path.name.endswith(".gz"):
            with gzip.open(schema_path, "rt", encoding="utf-8") as f:
                raw = json.load(f)
        else:
            with open(schema_path, encoding="utf-8") as f:
                raw = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load schema from %s: %s", schema_path, exc)
        return None

    provider_schemas = raw.get("provider_schemas", {})
    if not provider_schemas:
        return None

    provider_key = next(iter(provider_schemas))
    provider_data = provider_schemas[provider_key]
    provider_name = provider_key.rsplit("/", 1)[-1]

    resource_schemas = provider_data.get("resource_schemas", {})
    resource_types: dict[str, dict[str, Any]] = {}
    for resource_type, schema in resource_schemas.items():
        block = schema.get("block", {})
        resource_types[resource_type] = block.get("attributes", {})

    return ProviderSchemaInfo(
        provider_key=provider_key,
        provider_name=provider_name,
        format_version=raw.get("format_version", "unknown"),
        resource_types=resource_types,
    )


def infer_identity_keys(attributes: dict[str, Any]) -> list[str]:
    """Determine the best attribute keys for identifying a resource by name.

    Uses a priority list of well-known patterns, then falls back to any
    ``*_name`` or ``*_identifier`` string attribute.
    """

    # Try well-known patterns first.
    for pattern in _IDENTITY_KEY_PATTERNS:
        if pattern in attributes and _is_string_attr(attributes[pattern]):
            return [pattern]

    # Fallback: any string attribute ending in _name or _identifier.
    fallback: list[str] = []
    for attr_name in sorted(attributes):
        if not _is_string_attr(attributes[attr_name]):
            continue
        if attr_name.endswith("_name") or attr_name.endswith("_identifier"):
            fallback.append(attr_name)
    return fallback


def classify_resource_category(resource_type: str) -> str:
    """Classify a Terraform resource type into a service category.

    Strips the provider prefix (``aws_``, ``google_``, etc.) and matches the
    remaining service tokens against ``SERVICE_CATEGORIES``.
    """

    _, _, service_part = resource_type.partition("_")
    if not service_part:
        return "infrastructure"

    # Try progressively shorter token sequences.
    tokens = service_part.split("_")
    for length in range(len(tokens), 0, -1):
        prefix = "_".join(tokens[:length])
        if prefix in SERVICE_CATEGORIES:
            return SERVICE_CATEGORIES[prefix]

    return "infrastructure"


def _is_string_attr(attr: Any) -> bool:
    """Return True when a schema attribute definition is a simple string type."""

    if not isinstance(attr, dict):
        return False
    return attr.get("type") == "string"


__all__ = [
    "SERVICE_CATEGORIES",
    "ProviderSchemaInfo",
    "classify_resource_category",
    "infer_identity_keys",
    "load_provider_schema",
]
