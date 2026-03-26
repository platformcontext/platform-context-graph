"""Platform graph materialization helpers used by workload building."""

from __future__ import annotations

import re
from typing import Any, Iterable

_NON_PLATFORM_IDENTIFIERS = {
    "alerts",
    "current",
    "default",
    "eks",
    "ingress",
    "main",
    "pagerduty",
    "pipeline",
    "private",
    "private-regionless",
    "public",
    "terraform_state",
}
_ECS_CLUSTER_MODULE_PATTERNS = (
    "batch-compute-resource/aws",
    "ecs-cluster/aws",
)
_EKS_CLUSTER_MODULE_PATTERNS = (
    "terraform-aws-modules/eks/aws",
    "eks-blueprints",
    "eks-cluster",
)
_NON_CLUSTER_MODULE_PATTERNS = (
    "ecs-application/aws",
    "iam-role-for-service-accounts-eks",
)
_TERRAFORM_PLATFORM_KIND_PATTERNS = {
    "ecs": (_ECS_CLUSTER_MODULE_PATTERNS, ("aws_ecs_cluster",)),
    "eks": (_EKS_CLUSTER_MODULE_PATTERNS, ("aws_eks_cluster",)),
}
_TERRAFORM_CLUSTER_NAME_RE = re.compile(r'\bcluster_name\b\s*=\s*"([^"]+)"', re.IGNORECASE)
_TERRAFORM_NAME_RE = re.compile(r'\bname\b\s*=\s*"([^"]+)"', re.IGNORECASE)
_GITOPS_EXPLICIT_PLATFORM_KEYS = {
    "destinationClusterName",
    "destinationCluster",
    "clusterName",
    "cluster",
    "cluster_name",
}


def _normalize_token(value: str | None) -> str | None:
    """Return a lower-cased trimmed token or ``None`` when empty."""

    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def materialize_runtime_platform(
    session: Any,
    *,
    instance_id: str,
    environment: str,
    workload_name: str,
    resource_kinds: Iterable[str],
) -> None:
    """Attach a workload instance to a platform node when runtime signal exists."""

    if not environment.strip():
        return
    platform_kind = infer_runtime_platform_kind(resource_kinds)
    if platform_kind is None:
        return
    platform_name = environment.strip()
    platform_id = canonical_platform_id(
        kind=platform_kind,
        provider=None,
        name=platform_name,
        environment=environment,
        region=None,
        locator=None,
    )
    if platform_id is None:
        return
    session.run(
        """
        MATCH (i:WorkloadInstance {id: $instance_id})
        MERGE (p:Platform {id: $platform_id})
        SET p.type = 'platform',
            p.name = $platform_name,
            p.kind = $platform_kind,
            p.provider = $platform_provider,
            p.environment = $environment,
            p.region = $platform_region,
            p.locator = $platform_locator
        MERGE (i)-[rel:RUNS_ON]->(p)
        SET rel.confidence = 1.0,
            rel.reason = 'Workload instance runs on inferred platform'
        """,
        environment=environment,
        instance_id=instance_id,
        platform_id=platform_id,
        platform_kind=platform_kind,
        platform_locator=None,
        platform_name=platform_name,
        platform_provider=None,
        platform_region=None,
    )


def materialize_infrastructure_platforms(session: Any) -> None:
    """Attach infrastructure repositories to inferred platform nodes."""

    platform_rows = session.run(
        """
        MATCH (repo:Repository)
        OPTIONAL MATCH (repo)-[:CONTAINS*]->(:File)-[:CONTAINS]->(ds:TerraformDataSource)
        OPTIONAL MATCH (repo)-[:CONTAINS*]->(:File)-[:CONTAINS]->(mod:TerraformModule)
        OPTIONAL MATCH (repo)-[:CONTAINS*]->(:File)-[:CONTAINS]->(tf:TerraformResource)
        WITH repo,
             collect(DISTINCT toLower(coalesce(ds.data_type, ''))) as data_types,
             collect(DISTINCT toLower(coalesce(ds.data_name, ''))) as data_names,
             collect(DISTINCT toLower(coalesce(mod.source, ''))) as module_sources,
             collect(DISTINCT toLower(coalesce(mod.name, ''))) as module_names,
             collect(DISTINCT toLower(coalesce(tf.resource_type, ''))) as resource_types,
             collect(DISTINCT toLower(coalesce(tf.resource_name, ''))) as resource_names
        WHERE any(data_type IN data_types WHERE data_type <> '')
           OR any(module_source IN module_sources WHERE module_source <> '')
           OR any(resource_type IN resource_types WHERE resource_type <> '')
        RETURN repo.id as repo_id,
               repo.name as repo_name,
               data_types,
               data_names,
               module_sources,
               module_names,
               resource_types,
               resource_names
        ORDER BY repo.name
        """
    ).data()

    for row in platform_rows:
        descriptor = infer_infrastructure_platform_descriptor(
            data_types=row.get("data_types", []),
            data_names=row.get("data_names", []),
            module_sources=row.get("module_sources", []),
            module_names=row.get("module_names", []),
            resource_types=row.get("resource_types", []),
            resource_names=row.get("resource_names", []),
            repo_name=str(row.get("repo_name") or ""),
        )
        if descriptor is None:
            continue
        session.run(
            """
            MATCH (repo:Repository {id: $repo_id})
            MERGE (p:Platform {id: $platform_id})
            SET p.type = 'platform',
                p.name = $platform_name,
                p.kind = $platform_kind,
                p.provider = $platform_provider,
                p.environment = $platform_environment,
                p.region = $platform_region,
                p.locator = $platform_locator
            MERGE (repo)-[rel:PROVISIONS_PLATFORM]->(p)
            SET rel.confidence = 0.98,
                rel.reason = 'Terraform cluster and module data declare platform provisioning'
            """,
            platform_environment=descriptor["platform_environment"],
            platform_id=descriptor["platform_id"],
            platform_kind=descriptor["platform_kind"],
            platform_locator=descriptor["platform_locator"],
            platform_name=descriptor["platform_name"],
            platform_provider=descriptor["platform_provider"],
            platform_region=descriptor["platform_region"],
            repo_id=row.get("repo_id"),
        )


def infer_runtime_platform_kind(resource_kinds: Iterable[str]) -> str | None:
    """Infer a runtime platform kind from workload resource kinds."""

    normalized = {str(kind).lower() for kind in resource_kinds if str(kind).strip()}
    if not normalized:
        return None
    if normalized.intersection({"deployment", "service", "statefulset", "daemonset"}):
        return "kubernetes"
    return None


def infer_terraform_platform_kind(content: str) -> str | None:
    """Infer a Terraform platform kind from portable cluster/module signals."""

    lower_content = content.lower()
    for kind, (_, resource_patterns) in _TERRAFORM_PLATFORM_KIND_PATTERNS.items():
        if any(resource_pattern in lower_content for resource_pattern in resource_patterns):
            return kind
    if any(pattern in lower_content for pattern in _ECS_CLUSTER_MODULE_PATTERNS):
        return "ecs"
    if any(pattern in lower_content for pattern in _EKS_CLUSTER_MODULE_PATTERNS):
        return "eks"
    return None


def extract_terraform_platform_name(content: str) -> str | None:
    """Extract a stable Terraform platform name from cluster-like fields."""

    for pattern in (_TERRAFORM_CLUSTER_NAME_RE, _TERRAFORM_NAME_RE):
        match = pattern.search(content)
        if not match:
            continue
        candidate = match.group(1).strip()
        if candidate and candidate.lower() not in _NON_PLATFORM_IDENTIFIERS:
            return candidate
    return None


def infer_gitops_platform_kind(*, repo_name: str, repo_slug: str | None, content: str) -> str | None:
    """Infer a platform kind from portable GitOps control-plane signals."""

    normalized_name = repo_name.lower()
    normalized_slug = (repo_slug or "").lower()
    lower_content = content.lower()
    if "eks" in normalized_name or "eks" in normalized_slug:
        return "eks"
    if "ecs" in normalized_name or "ecs" in normalized_slug:
        return "ecs"
    if any(key.lower() in lower_content for key in _GITOPS_EXPLICIT_PLATFORM_KEYS):
        return "kubernetes"
    return None


def infer_gitops_platform_id(
    *,
    repo_name: str,
    repo_slug: str | None,
    content: str,
    platform_name: str,
    environment: str | None = None,
    region: str | None = None,
    locator: str | None = None,
) -> str | None:
    """Build a canonical platform id from GitOps repo metadata and destination config."""

    platform_kind = infer_gitops_platform_kind(
        repo_name=repo_name,
        repo_slug=repo_slug,
        content=content,
    )
    if platform_kind is None:
        return None
    return canonical_platform_id(
        kind=platform_kind,
        provider="aws" if platform_kind in {"ecs", "eks"} else None,
        name=platform_name,
        environment=environment,
        region=region,
        locator=locator,
    )


def canonical_platform_id(
    *,
    kind: str,
    provider: str | None,
    name: str | None,
    environment: str | None,
    region: str | None,
    locator: str | None,
) -> str | None:
    """Build a canonical platform identifier without importing relationships."""

    normalized_kind = _normalize_token(kind)
    normalized_provider = _normalize_token(provider)
    normalized_name = _normalize_token(name)
    normalized_environment = _normalize_token(environment)
    normalized_region = _normalize_token(region)
    normalized_locator = _normalize_token(locator)

    discriminator = normalized_locator or normalized_name
    if discriminator is None and not (
        normalized_environment is not None and normalized_region is not None
    ):
        return None

    return (
        "platform:"
        f"{normalized_kind or 'none'}:"
        f"{normalized_provider or 'none'}:"
        f"{discriminator or 'none'}:"
        f"{normalized_environment or 'none'}:"
        f"{normalized_region or 'none'}"
    )


def infer_infrastructure_platform_descriptor(
    *,
    data_types: Iterable[str],
    data_names: Iterable[str],
    module_sources: Iterable[str],
    module_names: Iterable[str],
    resource_types: Iterable[str],
    resource_names: Iterable[str],
    repo_name: str,
) -> dict[str, str] | None:
    """Return a platform descriptor for infra repos when the signal is explicit."""

    normalized_data_types = [str(value).lower() for value in data_types if str(value).strip()]
    normalized_data_names = [str(value).strip() for value in data_names if str(value).strip()]
    normalized_module_sources = [
        str(value).lower() for value in module_sources if str(value).strip()
    ]
    normalized_module_names = [str(value).strip() for value in module_names if str(value).strip()]
    normalized_resource_types = [
        str(value).lower() for value in resource_types if str(value).strip()
    ]
    normalized_resource_names = [
        str(value).strip() for value in resource_names if str(value).strip()
    ]

    platform_kind: str | None = None
    if any("aws_ecs_cluster" == value for value in normalized_resource_types) or any(
        pattern in value for value in normalized_module_sources for pattern in _ECS_CLUSTER_MODULE_PATTERNS
    ):
        platform_kind = "ecs"
    elif any("aws_eks_cluster" == value for value in normalized_resource_types) or any(
        pattern in value for value in normalized_module_sources for pattern in _EKS_CLUSTER_MODULE_PATTERNS
    ):
        platform_kind = "eks"
    if platform_kind is None:
        return None

    if any(
        pattern in value
        for value in normalized_module_sources
        for pattern in _NON_CLUSTER_MODULE_PATTERNS
    ):
        return None

    platform_provider = "aws" if any(
        value.startswith("aws_")
        for value in normalized_data_types + normalized_resource_types
    ) else None
    platform_name = _choose_platform_name(
        resource_names=normalized_resource_names,
        data_names=normalized_data_names,
        module_names=normalized_module_names,
        repo_name=repo_name,
    )
    if platform_name is None:
        return None
    platform_locator = f"cluster/{platform_name}"
    platform_id = canonical_platform_id(
        kind=platform_kind,
        provider=platform_provider,
        name=platform_name,
        environment=None,
        region=None,
        locator=platform_locator,
    )
    if platform_id is None:
        return None
    return {
        "platform_id": platform_id,
        "platform_kind": platform_kind,
        "platform_environment": None,
        "platform_locator": platform_locator,
        "platform_name": platform_name,
        "platform_provider": platform_provider,
        "platform_region": None,
    }


def _choose_platform_name(
    *,
    resource_names: Iterable[str],
    data_names: Iterable[str],
    module_names: Iterable[str],
    repo_name: str,
) -> str | None:
    """Choose a stable platform name from explicit cluster-like identifiers."""

    for value in list(resource_names) + list(data_names) + list(module_names):
        candidate = str(value).strip()
        if not candidate:
            continue
        normalized = candidate.lower()
        if normalized in _NON_PLATFORM_IDENTIFIERS:
            continue
        if normalized.startswith("aws_"):
            continue
        if "." in candidate and normalized.startswith("aws_"):
            continue
        return candidate
    return repo_name.strip() or None


__all__ = [
    "infer_infrastructure_platform_descriptor",
    "extract_terraform_platform_name",
    "infer_gitops_platform_id",
    "infer_gitops_platform_kind",
    "infer_terraform_platform_kind",
    "infer_runtime_platform_kind",
    "materialize_infrastructure_platforms",
    "materialize_runtime_platform",
]
