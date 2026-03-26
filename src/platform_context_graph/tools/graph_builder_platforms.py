"""Platform graph materialization helpers used by workload building."""

from __future__ import annotations

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
    platform_id = f"platform:{platform_kind}:{platform_name}"
    session.run(
        """
        MATCH (i:WorkloadInstance {id: $instance_id})
        MERGE (p:Platform {id: $platform_id})
        SET p.type = 'platform',
            p.name = $platform_name,
            p.kind = $platform_kind,
            p.provider = $platform_provider,
            p.environment = $environment
        MERGE (i)-[rel:RUNS_ON]->(p)
        SET rel.confidence = 1.0,
            rel.reason = 'Workload instance runs on inferred platform'
        """,
        environment=environment,
        instance_id=instance_id,
        platform_id=platform_id,
        platform_kind=platform_kind,
        platform_name=platform_name,
        platform_provider=None,
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
                p.provider = $platform_provider
            MERGE (repo)-[rel:PROVISIONS_PLATFORM]->(p)
            SET rel.confidence = 0.98,
                rel.reason = 'Terraform cluster and module data declare platform provisioning'
            """,
            platform_id=descriptor["platform_id"],
            platform_kind=descriptor["platform_kind"],
            platform_name=descriptor["platform_name"],
            platform_provider=descriptor["platform_provider"],
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
    platform_id = f"platform:{platform_provider or 'unknown'}:{platform_kind}:{platform_name}"
    return {
        "platform_id": platform_id,
        "platform_kind": platform_kind,
        "platform_name": platform_name,
        "platform_provider": platform_provider,
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
    "infer_runtime_platform_kind",
    "materialize_infrastructure_platforms",
    "materialize_runtime_platform",
]
