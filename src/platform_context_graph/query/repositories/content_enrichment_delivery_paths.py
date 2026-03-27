"""Delivery-path derivation helpers for enriched repository context."""

from __future__ import annotations

from typing import Any

_GITOPS_DELIVERY_MODES = frozenset({"eks_gitops", "eks_gitops_rollback"})
_DIRECT_DELIVERY_MODES = frozenset(
    {"continuous_deployment", "image_build_push", "deployment_verification"}
)
_KUBERNETES_PLATFORM_KINDS = frozenset({"eks", "kubernetes"})


def summarize_delivery_paths(
    *,
    delivery_workflows: dict[str, Any],
    platforms: list[dict[str, Any]],
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize workflow hints into higher-level delivery paths."""

    paths: list[dict[str, Any]] = []
    github_actions = (
        delivery_workflows.get("github_actions")
        if isinstance(delivery_workflows.get("github_actions"), dict)
        else {}
    )
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
                platforms=_filter_platforms(
                    platforms, include_kinds=_KUBERNETES_PLATFORM_KINDS
                ),
                deployment_sources=_repository_names(deploys_from),
                config_sources=_repository_names(discovers_config_in),
                provisioning_repositories=[],
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
                platforms=_filter_platforms(
                    platforms, exclude_kinds=_KUBERNETES_PLATFORM_KINDS
                ),
                deployment_sources=[],
                config_sources=[],
                provisioning_repositories=_repository_names(provisioned_by),
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
                platforms=_filter_platforms(
                    platforms, exclude_kinds=_KUBERNETES_PLATFORM_KINDS
                ),
                provisioning_repositories=_repository_names(provisioned_by),
            )
        )
    return [path for path in paths if path]


def _build_delivery_path(
    *,
    controller: str,
    path_kind: str,
    delivery_mode: str,
    command_rows: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    deployment_sources: list[str],
    config_sources: list[str],
    provisioning_repositories: list[str],
    summary_prefix: str,
) -> dict[str, Any]:
    """Build one normalized delivery-path payload."""

    commands = _ordered_unique(
        str(row.get("command") or "").strip() for row in command_rows
    )
    supporting_workflows = _ordered_unique(
        str(row.get("workflow") or "").strip() for row in command_rows
    )
    platform_kinds = _ordered_unique(
        str(row.get("kind") or "").strip() for row in platforms
    )
    platform_ids = _ordered_unique(
        str(row.get("id") or "").strip() for row in platforms
    )
    environments = _ordered_unique(
        str(row.get("environment") or "").strip() for row in platforms
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
    environments = _ordered_unique(
        str(row.get("environment") or "").strip() for row in platforms
    )
    return {
        "path_kind": "direct",
        "controller": "jenkins",
        "delivery_mode": "jenkins_pipeline",
        "commands": [],
        "supporting_workflows": _ordered_unique(
            str(row.get("relative_path") or "").strip() for row in jenkins_rows
        ),
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
        kind = platform_kinds[0].strip().lower()
        if kind == "eks":
            return "EKS platforms"
        if kind == "ecs":
            return "ECS platforms"
        if kind == "kubernetes":
            return "Kubernetes platforms"
        return f"{kind} platforms"
    rendered = ", ".join(kind.upper() for kind in platform_kinds)
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
