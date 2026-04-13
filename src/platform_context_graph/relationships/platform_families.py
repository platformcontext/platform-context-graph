"""Generic Terraform runtime-family definitions and lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TerraformRuntimeFamily:
    """Describe one Terraform-managed runtime family."""

    kind: str
    provider: str | None
    display_name: str
    name_hints: tuple[str, ...]
    cluster_module_patterns: tuple[str, ...]
    cluster_resource_types: tuple[str, ...]
    service_module_patterns: tuple[str, ...]
    non_cluster_module_patterns: tuple[str, ...]


_RUNTIME_FAMILIES: tuple[TerraformRuntimeFamily, ...] = (
    TerraformRuntimeFamily(
        kind="ecs",
        provider="aws",
        display_name="ECS",
        name_hints=("ecs", "fargate"),
        cluster_module_patterns=("batch-compute-resource/aws", "ecs-cluster/aws"),
        cluster_resource_types=("aws_ecs_cluster",),
        service_module_patterns=("ecs-application/aws",),
        non_cluster_module_patterns=("ecs-application/aws",),
    ),
    TerraformRuntimeFamily(
        kind="eks",
        provider="aws",
        display_name="EKS",
        name_hints=("eks",),
        cluster_module_patterns=(
            "terraform-aws-modules/eks/aws",
            "eks-blueprints",
            "eks-cluster",
        ),
        cluster_resource_types=("aws_eks_cluster",),
        service_module_patterns=(),
        non_cluster_module_patterns=("iam-role-for-service-accounts-eks",),
    ),
    TerraformRuntimeFamily(
        kind="lambda",
        provider="aws",
        display_name="Lambda",
        name_hints=("lambda", "serverless"),
        cluster_module_patterns=(),
        cluster_resource_types=("aws_lambda_function",),
        service_module_patterns=("lambda-function", "serverless-function"),
        non_cluster_module_patterns=(),
    ),
    TerraformRuntimeFamily(
        kind="cloudflare_workers",
        provider="cloudflare",
        display_name="Cloudflare Workers",
        name_hints=("cloudflare", "workers"),
        cluster_module_patterns=(),
        cluster_resource_types=("cloudflare_workers_script",),
        service_module_patterns=("cloudflare-worker",),
        non_cluster_module_patterns=(),
    ),
    TerraformRuntimeFamily(
        kind="gke",
        provider="gcp",
        display_name="GKE",
        name_hints=("gke",),
        cluster_module_patterns=(
            "terraform-google-modules/kubernetes-engine",
            "gke-cluster",
        ),
        cluster_resource_types=("google_container_cluster",),
        service_module_patterns=(),
        non_cluster_module_patterns=(),
    ),
    TerraformRuntimeFamily(
        kind="aks",
        provider="azure",
        display_name="AKS",
        name_hints=("aks",),
        cluster_module_patterns=(
            "Azure/aks/azurerm",
            "aks-cluster",
        ),
        cluster_resource_types=("azurerm_kubernetes_cluster",),
        service_module_patterns=(),
        non_cluster_module_patterns=(),
    ),
    TerraformRuntimeFamily(
        kind="cloud_run",
        provider="gcp",
        display_name="Cloud Run",
        name_hints=("cloud-run", "cloud_run", "cloudrun"),
        cluster_module_patterns=(),
        cluster_resource_types=(
            "google_cloud_run_service",
            "google_cloud_run_v2_service",
        ),
        service_module_patterns=("cloud-run",),
        non_cluster_module_patterns=(),
    ),
    TerraformRuntimeFamily(
        kind="container_apps",
        provider="azure",
        display_name="Azure Container Apps",
        name_hints=("container-apps", "container_apps"),
        cluster_module_patterns=(),
        cluster_resource_types=("azurerm_container_app",),
        service_module_patterns=(),
        non_cluster_module_patterns=(),
    ),
)


def iter_runtime_families() -> tuple[TerraformRuntimeFamily, ...]:
    """Return the registered Terraform runtime families."""

    return _RUNTIME_FAMILIES


def lookup_runtime_family(kind: str) -> TerraformRuntimeFamily | None:
    """Return one registered runtime family by normalized kind."""

    normalized = str(kind).strip().lower()
    for family in _RUNTIME_FAMILIES:
        if family.kind == normalized:
            return family
    return None


def infer_terraform_runtime_family_kind(content: str) -> str | None:
    """Infer the runtime family kind from Terraform content."""

    lower_content = content.lower()
    for family in _RUNTIME_FAMILIES:
        if any(
            resource_type in lower_content
            for resource_type in family.cluster_resource_types
        ):
            return family.kind
        if any(pattern in lower_content for pattern in family.cluster_module_patterns):
            return family.kind
    return None


def infer_runtime_family_kind_from_identifiers(
    values: Iterable[str | None],
) -> str | None:
    """Infer a runtime family kind from repo names, slugs, or other identifiers."""

    normalized_values = [
        str(value).strip().lower() for value in values if str(value).strip()
    ]
    for family in _RUNTIME_FAMILIES:
        if any(
            hint in normalized_value
            for normalized_value in normalized_values
            for hint in family.name_hints
        ):
            return family.kind
    return None


def infer_infrastructure_runtime_family_kind(
    *,
    resource_types: Iterable[str],
    module_sources: Iterable[str],
) -> str | None:
    """Infer a runtime family for infra repos with explicit cluster signals."""

    normalized_resource_types = {
        str(value).strip().lower() for value in resource_types if str(value).strip()
    }
    normalized_module_sources = {
        str(value).strip().lower() for value in module_sources if str(value).strip()
    }
    for family in _RUNTIME_FAMILIES:
        has_cluster_signal = any(
            resource_type in normalized_resource_types
            for resource_type in family.cluster_resource_types
        ) or any(
            pattern in module_source
            for module_source in normalized_module_sources
            for pattern in family.cluster_module_patterns
        )
        if not has_cluster_signal:
            continue
        if any(
            pattern in module_source
            for module_source in normalized_module_sources
            for pattern in family.non_cluster_module_patterns
        ):
            continue
        return family.kind
    return None


def matches_service_module_source(source: str, *, kind: str) -> bool:
    """Return whether one module source matches the registered service patterns."""

    family = lookup_runtime_family(kind)
    if family is None or not family.service_module_patterns:
        return False
    normalized = source.strip().lower()
    return any(pattern in normalized for pattern in family.service_module_patterns)


def terraform_platform_evidence_kind(kind: str, *, scope: str) -> str:
    """Build a stable Terraform evidence kind for one runtime family and scope."""

    normalized_kind = str(kind).strip().upper() or "UNKNOWN"
    normalized_scope = str(scope).strip().upper() or "UNKNOWN"
    return f"TERRAFORM_{normalized_kind}_{normalized_scope}"


def format_platform_kind_label(kind: str) -> str:
    """Return a human-readable label for one platform kind."""

    normalized = str(kind).strip().lower()
    family = lookup_runtime_family(normalized)
    if family is not None:
        return family.display_name
    if normalized == "kubernetes":
        return "Kubernetes"
    if normalized == "lambda":
        return "Lambda"
    if normalized == "cloudflare_workers":
        return "Cloudflare Workers"
    return normalized.upper() if normalized else ""


__all__ = [
    "TerraformRuntimeFamily",
    "format_platform_kind_label",
    "infer_infrastructure_runtime_family_kind",
    "infer_runtime_family_kind_from_identifiers",
    "infer_terraform_runtime_family_kind",
    "iter_runtime_families",
    "lookup_runtime_family",
    "matches_service_module_source",
    "terraform_platform_evidence_kind",
]
