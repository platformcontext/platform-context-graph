"""Generic Terraform runtime-family definitions and lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TerraformRuntimeFamily:
    """Describe one Terraform-managed runtime family."""

    kind: str
    provider: str | None
    cluster_module_patterns: tuple[str, ...]
    cluster_resource_types: tuple[str, ...]
    service_module_patterns: tuple[str, ...]
    non_cluster_module_patterns: tuple[str, ...]


_RUNTIME_FAMILIES: tuple[TerraformRuntimeFamily, ...] = (
    TerraformRuntimeFamily(
        kind="ecs",
        provider="aws",
        cluster_module_patterns=("batch-compute-resource/aws", "ecs-cluster/aws"),
        cluster_resource_types=("aws_ecs_cluster",),
        service_module_patterns=("ecs-application/aws",),
        non_cluster_module_patterns=("ecs-application/aws",),
    ),
    TerraformRuntimeFamily(
        kind="eks",
        provider="aws",
        cluster_module_patterns=(
            "terraform-aws-modules/eks/aws",
            "eks-blueprints",
            "eks-cluster",
        ),
        cluster_resource_types=("aws_eks_cluster",),
        service_module_patterns=(),
        non_cluster_module_patterns=("iam-role-for-service-accounts-eks",),
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
        if any(
            pattern in lower_content for pattern in family.cluster_module_patterns
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


__all__ = [
    "TerraformRuntimeFamily",
    "infer_infrastructure_runtime_family_kind",
    "infer_terraform_runtime_family_kind",
    "iter_runtime_families",
    "lookup_runtime_family",
    "matches_service_module_source",
]
