"""Delivery-path derivation helpers for enriched repository context."""

from __future__ import annotations

from typing import Any

from ...resolution.platform_families import format_platform_kind_label
from .content_enrichment_infrastructure_delivery import (
    build_infrastructure_delivery_paths,
)
from .content_enrichment_local_delivery import build_local_delivery_paths
from .content_enrichment_support import ordered_unique_environments

_GITOPS_DELIVERY_MODES = frozenset({"eks_gitops", "eks_gitops_rollback"})
_DIRECT_DELIVERY_MODES = frozenset(
    {"continuous_deployment", "image_build_push", "deployment_verification"}
)
_KUBERNETES_PLATFORM_KINDS = frozenset({"eks", "kubernetes"})


def summarize_delivery_paths(
    *,
    delivery_workflows: dict[str, Any],
    controller_driven_paths: list[dict[str, Any]] | None = None,
    platforms: list[dict[str, Any]],
    infrastructure: dict[str, Any] | None = None,
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    deployment_artifacts: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Summarize workflow hints into higher-level delivery paths."""

    paths: list[dict[str, Any]] = []
    controller_driven_paths = list(controller_driven_paths or [])
    github_actions = (
        delivery_workflows.get("github_actions")
        if isinstance(delivery_workflows.get("github_actions"), dict)
        else {}
    )
    github_actions_automation = _github_actions_automation_repositories(github_actions)
    github_actions_supporting = _github_actions_supporting_workflows(github_actions)
    command_rows = [
        row for row in github_actions.get("commands", []) if isinstance(row, dict)
    ]
    gitops_rows = [
        row
        for row in command_rows
        if str(row.get("delivery_mode") or "").strip() in _GITOPS_DELIVERY_MODES
    ]
    if gitops_rows:
        paths.append(
            _build_delivery_path(
                controller="github_actions",
                path_kind="gitops",
                delivery_mode="eks_gitops",
                command_rows=gitops_rows,
                supporting_workflows=None,
                platforms=_filter_platforms(
                    platforms, include_kinds=_KUBERNETES_PLATFORM_KINDS
                ),
                deployment_sources=_repository_names(deploys_from),
                config_sources=_repository_names(discovers_config_in),
                provisioning_repositories=[],
                automation_repositories=(
                    _automation_repository_names(gitops_rows)
                    or github_actions_automation
                ),
                summary_prefix="GitHub Actions drives a GitOps deployment path",
            )
        )
    elif github_actions_automation and deploys_from:
        gitops_platforms = _filter_platforms(
            platforms, include_kinds=_KUBERNETES_PLATFORM_KINDS
        )
        if gitops_platforms:
            paths.append(
                _build_delivery_path(
                    controller="github_actions",
                    path_kind="gitops",
                    delivery_mode="eks_gitops",
                    command_rows=[],
                    supporting_workflows=github_actions_supporting,
                    platforms=gitops_platforms,
                    deployment_sources=_repository_names(deploys_from),
                    config_sources=_repository_names(discovers_config_in),
                    provisioning_repositories=[],
                    automation_repositories=github_actions_automation,
                    summary_prefix="GitHub Actions drives a GitOps deployment path",
                )
            )
    direct_rows = [
        row
        for row in command_rows
        if str(row.get("delivery_mode") or "").strip() in _DIRECT_DELIVERY_MODES
    ]
    if direct_rows:
        paths.append(
            _build_delivery_path(
                controller="github_actions",
                path_kind="direct",
                delivery_mode="continuous_deployment",
                command_rows=direct_rows,
                supporting_workflows=None,
                platforms=_filter_platforms(
                    platforms, exclude_kinds=_KUBERNETES_PLATFORM_KINDS
                ),
                deployment_sources=[],
                config_sources=[],
                provisioning_repositories=_repository_names(provisioned_by),
                automation_repositories=(
                    _automation_repository_names(direct_rows)
                    or github_actions_automation
                ),
                summary_prefix="GitHub Actions drives a direct deployment path",
            )
        )
    elif github_actions_automation and provisioned_by:
        direct_platforms = _filter_platforms(
            platforms, exclude_kinds=_KUBERNETES_PLATFORM_KINDS
        )
        if direct_platforms:
            paths.append(
                _build_delivery_path(
                    controller="github_actions",
                    path_kind="direct",
                    delivery_mode="continuous_deployment",
                    command_rows=[],
                    supporting_workflows=github_actions_supporting,
                    platforms=direct_platforms,
                    deployment_sources=[],
                    config_sources=[],
                    provisioning_repositories=_repository_names(provisioned_by),
                    automation_repositories=github_actions_automation,
                    summary_prefix="GitHub Actions drives a direct deployment path",
                )
            )
    jenkins_rows = [
        row for row in delivery_workflows.get("jenkins", []) if isinstance(row, dict)
    ]
    if jenkins_rows:
        paths.append(
            _build_jenkins_delivery_path(
                jenkins_rows=jenkins_rows,
                controller_driven_paths=controller_driven_paths,
                platforms=_filter_platforms(
                    platforms, exclude_kinds=_KUBERNETES_PLATFORM_KINDS
                ),
                provisioning_repositories=_repository_names(provisioned_by),
            )
        )
    paths.extend(
        build_infrastructure_delivery_paths(
            infrastructure=infrastructure or {},
            platforms=platforms,
        )
    )
    paths.extend(
        build_local_delivery_paths(
            deployment_artifacts=deployment_artifacts or {},
            platforms=platforms,
        )
    )
    return [path for path in paths if path]


def _build_delivery_path(
    *,
    controller: str,
    path_kind: str,
    delivery_mode: str,
    command_rows: list[dict[str, Any]],
    supporting_workflows: list[str] | None,
    platforms: list[dict[str, Any]],
    deployment_sources: list[str],
    config_sources: list[str],
    provisioning_repositories: list[str],
    automation_repositories: list[str],
    summary_prefix: str,
) -> dict[str, Any]:
    """Build one normalized delivery-path payload."""

    commands = _ordered_unique(
        str(row.get("command") or "").strip() for row in command_rows
    )
    supporting_workflows = (
        _ordered_unique(supporting_workflows)
        if supporting_workflows is not None
        else _ordered_unique(
            str(row.get("workflow") or "").strip() for row in command_rows
        )
    )
    platform_kinds = _ordered_unique(
        str(row.get("kind") or "").strip() for row in platforms
    )
    platform_ids = _ordered_unique(
        str(row.get("id") or "").strip() for row in platforms
    )
    environments = ordered_unique_environments(
        [str(row.get("environment") or "").strip() for row in platforms]
    )
    summary = _delivery_path_summary(
        summary_prefix=summary_prefix,
        deployment_sources=deployment_sources,
        provisioning_repositories=provisioning_repositories,
        platform_kinds=platform_kinds,
    )
    return {
        "path_kind": path_kind,
        "controller": controller,
        "delivery_mode": delivery_mode,
        "commands": commands,
        "supporting_workflows": supporting_workflows,
        "automation_repositories": automation_repositories,
        "platform_kinds": platform_kinds,
        "platforms": platform_ids,
        "deployment_sources": deployment_sources,
        "config_sources": config_sources,
        "provisioning_repositories": provisioning_repositories,
        "environments": environments,
        "summary": summary,
    }


def _build_jenkins_delivery_path(
    *,
    jenkins_rows: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    provisioning_repositories: list[str],
) -> dict[str, Any]:
    """Build one normalized Jenkins delivery-path payload."""

    platform_kinds = _ordered_unique(
        str(row.get("kind") or "").strip() for row in platforms
    )
    platform_ids = _ordered_unique(
        str(row.get("id") or "").strip() for row in platforms
    )
    environments = ordered_unique_environments(
        [str(row.get("environment") or "").strip() for row in platforms]
    )
    controller_supporting_repositories = _ordered_unique(
        repository
        for row in controller_driven_paths
        if isinstance(row, dict) and str(row.get("controller_kind") or "") == "jenkins"
        for repository in row.get("supporting_repositories", [])
    )
    if controller_supporting_repositories:
        provisioning_repositories = controller_supporting_repositories
    return {
        "path_kind": "direct",
        "controller": "jenkins",
        "delivery_mode": "jenkins_pipeline",
        "commands": [],
        "supporting_workflows": _ordered_unique(
            str(row.get("relative_path") or "").strip() for row in jenkins_rows
        ),
        "automation_repositories": [],
        "platform_kinds": platform_kinds,
        "platforms": platform_ids,
        "deployment_sources": [],
        "config_sources": [],
        "provisioning_repositories": provisioning_repositories,
        "environments": environments,
        "summary": _delivery_path_summary(
            summary_prefix="Jenkins drives a direct deployment path",
            deployment_sources=[],
            provisioning_repositories=provisioning_repositories,
            platform_kinds=platform_kinds,
        ),
    }


def _filter_platforms(
    rows: list[dict[str, Any]],
    *,
    include_kinds: set[str] | frozenset[str] | None = None,
    exclude_kinds: set[str] | frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter platform rows by normalized platform kind."""

    filtered: list[dict[str, Any]] = []
    for row in rows:
        kind = str(row.get("kind") or "").strip().lower()
        if include_kinds is not None and kind not in include_kinds:
            continue
        if exclude_kinds is not None and kind in exclude_kinds:
            continue
        filtered.append(row)
    return filtered


def _repository_names(rows: list[dict[str, Any]]) -> list[str]:
    """Return ordered unique repository names from relationship rows."""

    return _ordered_unique(str(row.get("name") or "").strip() for row in rows)


def _automation_repository_names(rows: list[dict[str, Any]]) -> list[str]:
    """Return ordered unique automation repository names from workflow rows."""

    return _ordered_unique(
        str(row.get("automation_repository") or "").strip() for row in rows
    )


def _github_actions_automation_repositories(
    github_actions: dict[str, Any],
) -> list[str]:
    """Return ordered unique automation repositories from a GitHub Actions block."""

    return _ordered_unique(
        str(row.get("repository") or "").strip()
        for row in github_actions.get("automation_repositories", [])
        if isinstance(row, dict)
    )


def _github_actions_supporting_workflows(github_actions: dict[str, Any]) -> list[str]:
    """Return repo-local workflow filenames that hand off to automation repos."""

    return _ordered_unique(
        str(row.get("relative_path") or "").strip().split("/")[-1]
        for row in github_actions.get("workflows", [])
        if isinstance(row, dict)
    )


def _delivery_path_summary(
    *,
    summary_prefix: str,
    deployment_sources: list[str],
    provisioning_repositories: list[str],
    platform_kinds: list[str],
) -> str:
    """Render a short human-readable delivery-path summary."""

    summary = summary_prefix
    if deployment_sources:
        summary += f" through {', '.join(deployment_sources)}"
    elif provisioning_repositories:
        summary += f" through {', '.join(provisioning_repositories)}"
    platform_phrase = _platform_kind_phrase(platform_kinds)
    if platform_phrase:
        summary += f" onto {platform_phrase}"
    return summary + "."


def _platform_kind_phrase(platform_kinds: list[str]) -> str:
    """Return a pluralized platform phrase for one or more platform kinds."""

    if not platform_kinds:
        return ""
    if len(platform_kinds) == 1:
        rendered = format_platform_kind_label(platform_kinds[0])
        return f"{rendered} platforms" if rendered else ""
    rendered = ", ".join(format_platform_kind_label(kind) for kind in platform_kinds)
    return f"{rendered} platforms"


def _ordered_unique(values: Any) -> list[str]:
    """Return ordered unique non-empty strings."""

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


__all__ = ["summarize_delivery_paths"]
