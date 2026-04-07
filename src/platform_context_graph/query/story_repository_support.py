"""Small support helpers for repository story shaping."""

from __future__ import annotations

from typing import Any

from .story_investigation_hints import build_investigation_hints
from .story_shared import human_list


def dependency_label(row: Any) -> str:
    """Return a human-friendly dependency label from mixed response shapes."""

    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, dict):
        return ""
    for key in ("name", "repository", "repo_name", "label", "id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def subject_from_repository(context: dict[str, Any]) -> dict[str, Any]:
    """Build a portable repository subject from repository context."""

    repository = context.get("repository") or {}
    return {
        "id": repository.get("id"),
        "type": "repository",
        "name": repository.get("name") or repository.get("repo_slug") or "repository",
        "repo_slug": repository.get("repo_slug"),
        "remote_url": repository.get("remote_url"),
        "has_remote": repository.get("has_remote"),
    }


def focused_deployment_story(lines: list[str]) -> list[str]:
    """Return the direct deployment story lines without dependency sprawl."""

    focused: list[str] = []
    for value in lines:
        line = str(value).strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("shared config"):
            continue
        if lower.startswith("consumer repositories"):
            continue
        if "consumer-only repository" in lower:
            continue
        focused.append(line)
    return focused


def build_repository_deployment_overview(context: dict[str, Any]) -> dict[str, Any]:
    """Build a compact repository deployment overview from story inputs."""

    hostnames = list(context.get("hostnames") or [])
    api_surface = dict(context.get("api_surface") or {})
    platforms = list(context.get("platforms") or [])
    delivery_paths = list(context.get("delivery_paths") or [])
    controller_driven_paths = list(context.get("controller_driven_paths") or [])
    deployment_artifacts = dict(context.get("deployment_artifacts") or {})
    consumer_repositories = list(context.get("consumer_repositories") or [])
    observed_config_environments = list(
        context.get("observed_config_environments") or []
    )
    delivery_workflows = dict(context.get("delivery_workflows") or {})
    deploys_from = list(context.get("deploys_from") or [])
    discovers_config_in = list(context.get("discovers_config_in") or [])
    provisioned_by = list(context.get("provisioned_by") or [])
    provisions_dependencies_for = list(context.get("provisions_dependencies_for") or [])
    iac_relationships = list(context.get("iac_relationships") or [])
    deployment_chain = list(context.get("deployment_chain") or [])
    environments = list(context.get("environments") or [])
    relationships = list(context.get("relationships") or [])
    ecosystem = dict(context.get("ecosystem") or {})
    coverage = context.get("coverage")
    summary = context.get("summary")
    public_hostnames = [
        str(row.get("hostname") or "").strip()
        for row in hostnames
        if isinstance(row, dict) and str(row.get("hostname") or "").strip()
    ]
    internal_hostnames = [
        str(row.get("hostname") or "").strip()
        for row in hostnames
        if isinstance(row, dict)
        and str(row.get("visibility") or "").strip().lower() == "internal"
        and str(row.get("hostname") or "").strip()
    ]

    deployment_story: list[str] = []
    if public_hostnames:
        deployment_story.append(
            f"Public entrypoints: {human_list(public_hostnames, limit=5)}."
        )
    if api_surface.get("api_versions") or api_surface.get("docs_routes"):
        api_parts: list[str] = []
        versions = [str(v) for v in api_surface.get("api_versions") or [] if str(v)]
        docs_routes = [str(v) for v in api_surface.get("docs_routes") or [] if str(v)]
        if versions:
            api_parts.append(f"versions {human_list(versions)}")
        if docs_routes:
            api_parts.append(f"docs {human_list(docs_routes)}")
        deployment_story.append(f"API surface exposes {' and '.join(api_parts)}.")
    if delivery_paths:
        first = delivery_paths[0]
        delivery_mode = str(first.get("delivery_mode") or "").strip()
        controller = str(first.get("controller") or "").strip()
        deployment_sources = [
            str(value).strip()
            for value in first.get("deployment_sources") or []
            if str(value).strip()
        ]
        platform_kinds = [
            str(value).strip()
            for value in first.get("platform_kinds") or []
            if str(value).strip()
        ]
        parts: list[str] = []
        if controller:
            parts.append(controller)
        if delivery_mode:
            parts.append(delivery_mode)
        if deployment_sources:
            parts.append(f"from {human_list(deployment_sources)}")
        if platform_kinds:
            parts.append(f"onto {human_list(platform_kinds)}")
        if parts:
            deployment_story.append("Deployment flows through " + " ".join(parts) + ".")
    if controller_driven_paths and not delivery_paths:
        first = controller_driven_paths[0]
        controller_kind = str(first.get("controller_kind") or "").strip()
        automation_kind = str(first.get("automation_kind") or "").strip()
        entry_points = [
            str(value).strip()
            for value in first.get("entry_points") or []
            if str(value).strip()
        ]
        parts = [part for part in [controller_kind, automation_kind] if part]
        if entry_points:
            parts.append(f"via {human_list(entry_points)}")
        if parts:
            deployment_story.append(
                "Controller-driven delivery uses " + " ".join(parts) + "."
            )

    topology_story = list(deployment_story)
    if deployment_artifacts.get("config_paths"):
        topology_story.append(
            "Shared config paths include "
            + human_list(
                [
                    str(v)
                    for v in deployment_artifacts.get("config_paths") or []
                    if str(v)
                ]
            )
            + "."
        )
    if consumer_repositories:
        topology_story.append(
            "Consumer repositories include "
            + human_list(
                [
                    str(row.get("repository") or row.get("name") or "")
                    for row in consumer_repositories
                    if isinstance(row, dict)
                    and str(row.get("repository") or row.get("name") or "").strip()
                ]
            )
            + "."
        )

    return {
        "hostnames": hostnames,
        "internet_entrypoints": public_hostnames,
        "internal_entrypoints": internal_hostnames,
        "api_surface": {
            "docs_routes": list(api_surface.get("docs_routes") or []),
            "api_versions": list(api_surface.get("api_versions") or []),
            "spec_files": list(api_surface.get("spec_files") or []),
            "endpoint_count": api_surface.get("endpoint_count"),
            "endpoints": list(api_surface.get("endpoints") or []),
        },
        "observed_config_environments": observed_config_environments,
        "runtime_platforms": [
            {
                "id": row.get("id"),
                "kind": row.get("kind"),
                "provider": row.get("provider"),
                "environment": row.get("environment"),
                "name": row.get("name"),
            }
            for row in platforms
            if isinstance(row, dict)
        ],
        "delivery_workflows": delivery_workflows,
        "delivery_paths": delivery_paths,
        "controller_driven_paths": controller_driven_paths,
        "deployment_artifacts": deployment_artifacts or None,
        "consumer_repositories": consumer_repositories,
        "deploys_from": deploys_from,
        "discovers_config_in": discovers_config_in,
        "provisioned_by": provisioned_by,
        "provisions_dependencies_for": provisions_dependencies_for,
        "iac_relationships": iac_relationships,
        "deployment_chain": deployment_chain,
        "environments": environments,
        "relationships": relationships,
        "ecosystem": ecosystem or None,
        "coverage": coverage,
        "summary": summary,
        "deployment_story": deployment_story,
        "topology_story": topology_story,
    }


def build_repository_investigation_hints(
    *,
    subject_name: str,
    deploys_from: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build lightweight investigation hints for repository stories."""

    return build_investigation_hints(
        subject_name=subject_name,
        deploys_from=deploys_from,
        provisioned_by=provisioned_by,
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
    )
