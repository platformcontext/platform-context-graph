"""Infrastructure-backed delivery path derivation helpers."""

from __future__ import annotations

from typing import Any

from ...resolution.platform_families import format_platform_kind_label
from .content_enrichment_support import ordered_unique_strings

_CLOUDFORMATION_ECS_TYPES = frozenset(
    {"AWS::ECS::Cluster", "AWS::ECS::Service", "AWS::ECS::TaskDefinition"}
)
_CLOUDFORMATION_EKS_TYPES = frozenset({"AWS::EKS::Addon", "AWS::EKS::Cluster"})
_CLOUDFORMATION_SERVERLESS_TYPES = frozenset(
    {"AWS::Lambda::Function", "AWS::Serverless::Function"}
)
_CLOUDFORMATION_STACKSET_TYPES = frozenset({"AWS::CloudFormation::StackSet"})
_TERRAFORM_HELM_TYPES = frozenset({"helm_release"})
_TERRAFORM_KUBERNETES_PREFIX = "kubernetes_"
_TERRAFORM_ECS_MODULE_HINTS = ("ecs-application/aws", "ecs/service")
_KUBERNETES_PLATFORM_KINDS = frozenset({"eks", "kubernetes"})


def build_infrastructure_delivery_paths(
    *,
    infrastructure: dict[str, Any],
    platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build normalized delivery paths from infrastructure evidence."""

    cloudformation_resources = [
        row
        for row in infrastructure.get("cloudformation_resources", [])
        if isinstance(row, dict)
    ]
    if not cloudformation_resources:
        cloudformation_paths: list[dict[str, Any]] = []
    else:
        cloudformation_paths = _build_cloudformation_delivery_paths(
            cloudformation_resources=cloudformation_resources,
            platforms=platforms,
        )
    return [
        *cloudformation_paths,
        *_build_terraform_provider_paths(
            terraform_resources=[
                row
                for row in infrastructure.get("terraform_resources", [])
                if isinstance(row, dict)
            ],
            platforms=platforms,
        ),
        *_build_terraform_ecs_paths(
            terraform_modules=[
                row
                for row in infrastructure.get("terraform_modules", [])
                if isinstance(row, dict)
            ],
            terraform_resources=[
                row
                for row in infrastructure.get("terraform_resources", [])
                if isinstance(row, dict)
            ],
            platforms=platforms,
        ),
    ]


def _build_cloudformation_delivery_paths(
    *,
    cloudformation_resources: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build CloudFormation delivery paths for known runtime families."""

    paths: list[dict[str, Any]] = []
    paths.extend(
        _build_one_cloudformation_path(
            cloudformation_resources=cloudformation_resources,
            platforms=platforms,
            resource_types=_CLOUDFORMATION_ECS_TYPES,
            delivery_mode="cloudformation_ecs",
            platform_kinds={"ecs"},
            summary_label="CloudFormation ECS deployment",
        )
    )
    paths.extend(
        _build_one_cloudformation_path(
            cloudformation_resources=cloudformation_resources,
            platforms=platforms,
            resource_types=_CLOUDFORMATION_EKS_TYPES,
            delivery_mode="cloudformation_eks",
            platform_kinds={"eks", "kubernetes"},
            summary_label="CloudFormation EKS deployment",
        )
    )
    paths.extend(
        _build_one_cloudformation_path(
            cloudformation_resources=cloudformation_resources,
            platforms=platforms,
            resource_types=_CLOUDFORMATION_SERVERLESS_TYPES,
            delivery_mode="cloudformation_serverless",
            platform_kinds={"lambda", "serverless"},
            summary_label="CloudFormation serverless deployment",
        )
    )
    paths.extend(
        _build_one_cloudformation_path(
            cloudformation_resources=cloudformation_resources,
            platforms=platforms,
            resource_types=_CLOUDFORMATION_STACKSET_TYPES,
            delivery_mode="cloudformation_stackset",
            platform_kinds=set(),
            summary_label="CloudFormation StackSet deployment",
        )
    )
    return paths


def _build_one_cloudformation_path(
    *,
    cloudformation_resources: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    resource_types: set[str] | frozenset[str],
    delivery_mode: str,
    platform_kinds: set[str],
    summary_label: str,
) -> list[dict[str, Any]]:
    """Build one CloudFormation delivery path when matching evidence exists."""

    matched_resources = [
        row
        for row in cloudformation_resources
        if str(row.get("resource_type") or "").strip() in resource_types
    ]
    if not matched_resources:
        return []

    matched_platforms = [
        row
        for row in platforms
        if isinstance(row, dict)
        and (not platform_kinds or str(row.get("kind") or "").strip() in platform_kinds)
    ]
    deployment_sources = ordered_unique_strings(
        row.get("file") for row in matched_resources if row.get("file")
    )
    platform_ids = ordered_unique_strings(
        row.get("id") for row in matched_platforms if row.get("id")
    )
    resolved_platform_kinds = ordered_unique_strings(
        row.get("kind") for row in matched_platforms if row.get("kind")
    )
    environments = ordered_unique_strings(
        row.get("environment") for row in matched_platforms if row.get("environment")
    )
    return [
        {
            "path_kind": "direct",
            "controller": "cloudformation",
            "delivery_mode": delivery_mode,
            "commands": [],
            "supporting_workflows": [],
            "automation_repositories": [],
            "platform_kinds": resolved_platform_kinds,
            "platforms": platform_ids,
            "deployment_sources": deployment_sources,
            "config_sources": [],
            "provisioning_repositories": [],
            "environments": environments,
            "summary": _cloudformation_summary(
                delivery_label=summary_label,
                sources=deployment_sources,
                platform_kinds=resolved_platform_kinds,
            ),
        }
    ]


def _cloudformation_summary(
    *,
    delivery_label: str,
    sources: list[str],
    platform_kinds: list[str],
) -> str:
    """Render a stable summary for one CloudFormation delivery path."""

    summary = f"Indexed CloudFormation resources indicate a direct {delivery_label}"
    if sources:
        summary += f" path through {', '.join(sources)}"
    if platform_kinds:
        labels = ", ".join(format_platform_kind_label(kind) for kind in platform_kinds)
        summary += f" onto {labels} platforms"
    return summary + "."


def _build_terraform_provider_paths(
    *,
    terraform_resources: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build direct Terraform provider delivery paths."""

    paths: list[dict[str, Any]] = []
    paths.extend(
        _build_one_terraform_provider_path(
            terraform_resources=terraform_resources,
            platforms=platforms,
            resource_matcher=lambda row: str(row.get("resource_type") or "").strip()
            in _TERRAFORM_HELM_TYPES,
            delivery_mode="terraform_helm_provider",
            platform_kinds=_KUBERNETES_PLATFORM_KINDS,
            summary_label="Helm deployment",
        )
    )
    paths.extend(
        _build_one_terraform_provider_path(
            terraform_resources=terraform_resources,
            platforms=platforms,
            resource_matcher=lambda row: str(row.get("resource_type") or "")
            .strip()
            .startswith(_TERRAFORM_KUBERNETES_PREFIX),
            delivery_mode="terraform_kubernetes_provider",
            platform_kinds=_KUBERNETES_PLATFORM_KINDS,
            summary_label="Kubernetes provider deployment",
        )
    )
    return paths


def _build_one_terraform_provider_path(
    *,
    terraform_resources: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    resource_matcher: Any,
    delivery_mode: str,
    platform_kinds: set[str] | frozenset[str],
    summary_label: str,
) -> list[dict[str, Any]]:
    """Build one Terraform provider-backed direct delivery path."""

    matched_resources = [row for row in terraform_resources if resource_matcher(row)]
    if not matched_resources:
        return []
    matched_platforms = [
        row
        for row in platforms
        if isinstance(row, dict)
        and str(row.get("kind") or "").strip() in platform_kinds
    ]
    if not matched_platforms:
        return []
    deployment_sources = ordered_unique_strings(
        row.get("repository") for row in matched_resources if row.get("repository")
    )
    config_sources = ordered_unique_strings(
        row.get("file") for row in matched_resources if row.get("file")
    )
    return [
        {
            "path_kind": "direct",
            "controller": "terraform",
            "delivery_mode": delivery_mode,
            "commands": [],
            "supporting_workflows": [],
            "automation_repositories": [],
            "platform_kinds": ordered_unique_strings(
                row.get("kind") for row in matched_platforms if row.get("kind")
            ),
            "platforms": ordered_unique_strings(
                row.get("id") for row in matched_platforms if row.get("id")
            ),
            "deployment_sources": deployment_sources,
            "config_sources": config_sources,
            "provisioning_repositories": [],
            "environments": ordered_unique_strings(
                row.get("environment")
                for row in matched_platforms
                if row.get("environment")
            ),
            "summary": _terraform_summary(
                delivery_label=summary_label,
                sources=deployment_sources,
                platform_kinds=ordered_unique_strings(
                    row.get("kind") for row in matched_platforms if row.get("kind")
                ),
            ),
        }
    ]


def _build_terraform_ecs_paths(
    *,
    terraform_modules: list[dict[str, Any]],
    terraform_resources: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build direct ECS delivery paths from Terraform module evidence."""

    ecs_modules = [
        row
        for row in terraform_modules
        if any(
            hint in str(row.get("source") or "").strip()
            for hint in _TERRAFORM_ECS_MODULE_HINTS
        )
    ]
    ecs_resources = [
        row
        for row in terraform_resources
        if str(row.get("resource_type") or "").strip().startswith("aws_ecs_")
    ]
    if not ecs_modules and not ecs_resources:
        return []
    matched_platforms = [
        row
        for row in platforms
        if isinstance(row, dict) and str(row.get("kind") or "").strip() == "ecs"
    ]
    if not matched_platforms:
        return []
    deployment_sources = ordered_unique_strings(
        [
            *(row.get("repository") for row in ecs_modules if row.get("repository")),
            *(row.get("repository") for row in ecs_resources if row.get("repository")),
        ]
    )
    config_sources = ordered_unique_strings(
        row.get("file") for row in ecs_resources if row.get("file")
    )
    return [
        {
            "path_kind": "direct",
            "controller": "terraform",
            "delivery_mode": "ecs_service_deployment",
            "commands": [],
            "supporting_workflows": [],
            "automation_repositories": [],
            "platform_kinds": ["ecs"],
            "platforms": ordered_unique_strings(
                row.get("id") for row in matched_platforms if row.get("id")
            ),
            "deployment_sources": deployment_sources,
            "config_sources": config_sources,
            "provisioning_repositories": [],
            "environments": ordered_unique_strings(
                row.get("environment")
                for row in matched_platforms
                if row.get("environment")
            ),
            "summary": _terraform_summary(
                delivery_label="ECS service deployment",
                sources=deployment_sources,
                platform_kinds=["ecs"],
            ),
        }
    ]


def _terraform_summary(
    *,
    delivery_label: str,
    sources: list[str],
    platform_kinds: list[str],
) -> str:
    """Render a stable summary for one Terraform-backed delivery path."""

    summary = f"Indexed Terraform resources indicate a direct {delivery_label}"
    if sources:
        summary += f" path through {', '.join(sources)}"
    if platform_kinds:
        labels = ", ".join(format_platform_kind_label(kind) for kind in platform_kinds)
        summary += f" onto {labels} platforms"
    return summary + "."


__all__ = ["build_infrastructure_delivery_paths"]
