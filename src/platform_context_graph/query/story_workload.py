"""Workload and service story contract helpers."""

from __future__ import annotations

from typing import Any

from .story_documentation import (
    build_documentation_overview,
    summarize_documentation_overview,
)
from .story_gitops import build_gitops_overview, summarize_gitops_overview
from .story_shared import human_list, portable_story_value, story_section
from .story_support import build_support_overview, summarize_support_overview


def _normalize_environment(value: Any) -> str:
    """Return a normalized environment token for story comparisons."""

    return str(value or "").strip().lower()


def _entrypoint_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    """Return a stable identity tuple for one entrypoint row."""

    return (
        str(row.get("hostname") or "").strip(),
        str(row.get("path") or "").strip(),
        str(row.get("relative_path") or "").strip(),
    )


def _api_surface_entrypoints(api_surface: dict[str, Any]) -> list[dict[str, Any]]:
    """Return entrypoint-like rows derived from API docs and endpoint evidence."""

    entrypoints: list[dict[str, Any]] = []
    for route in api_surface.get("docs_routes") or []:
        if not str(route).strip():
            continue
        entrypoints.append(
            {
                "path": str(route).strip(),
                "entrypoint_kind": "docs_route",
                "visibility": "internal",
            }
        )
    for row in api_surface.get("endpoints") or []:
        if not isinstance(row, dict) or not str(row.get("path") or "").strip():
            continue
        entrypoints.append(
            {
                "path": str(row.get("path") or "").strip(),
                "relative_path": row.get("relative_path"),
                "entrypoint_kind": "api_endpoint",
                "visibility": "internal",
            }
        )
    return entrypoints


def _entrypoint_sort_key(
    row: dict[str, Any], *, selected_environment: str | None
) -> tuple[int, int, str]:
    """Return a stable ranking for story entrypoints.

    Public hostnames for the selected environment rank highest, followed by
    health/status endpoints, docs routes, internal hostnames, and then generic
    API paths.
    """

    normalized_selected_environment = _normalize_environment(selected_environment)
    normalized_row_environment = _normalize_environment(row.get("environment"))
    environment_rank = 1
    if normalized_selected_environment and (
        normalized_row_environment == normalized_selected_environment
    ):
        environment_rank = 0
    elif normalized_row_environment:
        environment_rank = 2

    hostname = str(row.get("hostname") or "").strip()
    path = str(row.get("path") or "").strip()
    visibility = str(row.get("visibility") or "").strip().lower()
    entrypoint_kind = str(row.get("entrypoint_kind") or "").strip().lower()
    normalized_path = path.lower()

    if hostname and visibility == "public":
        category_rank = 0
    elif any(
        token in normalized_path for token in ("health", "status", "version", "ready")
    ):
        category_rank = 1
    elif entrypoint_kind == "docs_route":
        category_rank = 2
    elif hostname:
        category_rank = 3
    else:
        category_rank = 4

    label = hostname or path or str(row.get("name") or "").strip()
    return (category_rank, environment_rank, label)


def _rank_entrypoints(
    entrypoints: list[dict[str, Any]], *, selected_environment: str | None
) -> list[dict[str, Any]]:
    """Return deduped story entrypoints in support-friendly priority order."""

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in sorted(
        [row for row in entrypoints if isinstance(row, dict)],
        key=lambda row: _entrypoint_sort_key(
            row,
            selected_environment=selected_environment,
        ),
    ):
        identity = _entrypoint_identity(row)
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def _selected_environment_for_story(
    *,
    selected_instance: dict[str, Any] | None,
    context: dict[str, Any],
    entrypoints: list[dict[str, Any]],
) -> str | None:
    """Return the best environment token available for one story response."""

    if isinstance(selected_instance, dict):
        environment = str(selected_instance.get("environment") or "").strip()
        if environment:
            return environment

    candidate_values = [
        *[
            str(row.get("environment") or "").strip()
            for row in entrypoints
            if isinstance(row, dict) and str(row.get("environment") or "").strip()
        ],
        *[
            str(value).strip()
            for value in context.get("observed_config_environments") or []
            if str(value).strip()
        ],
        *[
            str(value).strip()
            for value in context.get("environments") or []
            if str(value).strip()
        ],
    ]
    normalized_candidates: dict[str, str] = {}
    for value in candidate_values:
        normalized_value = _normalize_environment(value)
        if normalized_value and normalized_value not in normalized_candidates:
            normalized_candidates[normalized_value] = value
    if len(normalized_candidates) == 1:
        return next(iter(normalized_candidates.values()))
    return None


def _build_workload_deployment_overview(
    *,
    context: dict[str, Any],
    selected_instance: dict[str, Any] | None,
    instances: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    api_surface: dict[str, Any],
    cloud_resources: list[dict[str, Any]],
    shared_resources: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    requested_as: str | None,
) -> dict[str, Any]:
    """Build the deployment overview portion of a workload or service story."""

    hostnames = [
        row for row in entrypoints if isinstance(row, dict) and row.get("hostname")
    ]
    internet_entrypoints = [
        row
        for row in hostnames
        if str(row.get("visibility") or "").strip().lower() == "public"
    ]
    internal_entrypoints = [
        row
        for row in hostnames
        if str(row.get("visibility") or "").strip().lower() != "public"
    ]
    return {
        "instances": [selected_instance] if selected_instance else instances,
        "repositories": repositories,
        "entrypoints": entrypoints,
        "hostnames": hostnames,
        "internet_entrypoints": internet_entrypoints,
        "internal_entrypoints": internal_entrypoints,
        "api_surface": {
            "docs_routes": list(api_surface.get("docs_routes") or []),
            "api_versions": list(api_surface.get("api_versions") or []),
            "spec_files": list(api_surface.get("spec_files") or []),
            "endpoint_count": api_surface.get("endpoint_count"),
            "endpoints": list(api_surface.get("endpoints") or []),
        },
        "delivery_paths": list(context.get("delivery_paths") or []),
        "controller_driven_paths": list(context.get("controller_driven_paths") or []),
        "deployment_artifacts": dict(context.get("deployment_artifacts") or {}) or None,
        "observed_config_environments": list(
            context.get("observed_config_environments") or []
        ),
        "environments": list(context.get("environments") or []),
        "cloud_resources": cloud_resources,
        "shared_resources": shared_resources,
        "dependencies": dependencies,
        "evidence": evidence,
        **({"requested_as": requested_as} if requested_as else {}),
    }


def _entrypoint_labels(entrypoints: list[dict[str, Any]]) -> list[str]:
    """Return human-friendly labels for workload entrypoints."""

    labels: list[str] = []
    for row in entrypoints:
        if not isinstance(row, dict):
            continue
        label = (
            row.get("hostname") or row.get("path") or row.get("url") or row.get("name")
        )
        if isinstance(label, str) and label:
            labels.append(label)
    return labels


def build_workload_story_response(
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build the structured story contract for one workload or service."""

    subject = dict(context.get("workload") or {})
    if not subject:
        return context

    selected_instance = context.get("instance")
    instances = list(context.get("instances") or [])
    repositories = list(context.get("repositories") or [])
    cloud_resources = list(context.get("cloud_resources") or [])
    shared_resources = list(context.get("shared_resources") or [])
    dependencies = list(context.get("dependencies") or [])
    api_surface = dict(context.get("api_surface") or {})
    selected_environment = _selected_environment_for_story(
        selected_instance=selected_instance,
        context=context,
        entrypoints=list(context.get("entrypoints") or []),
    )
    entrypoints = _rank_entrypoints(
        [
            *list(context.get("entrypoints") or []),
            *_api_surface_entrypoints(api_surface),
        ],
        selected_environment=selected_environment,
    )
    evidence = list(context.get("evidence") or [])
    requested_as = context.get("requested_as")

    story: list[str] = []
    if selected_instance:
        environment_name = selected_instance.get("environment") or "unknown"
        story.append(
            f"{subject['name']} has an environment-scoped instance for {environment_name}."
        )
    elif instances:
        story.append(
            f"{subject['name']} has {len(instances)} known workload instances across environments."
        )
    if repositories:
        story.append(
            f"Owned by repositories {human_list([str(row.get('name') or '') for row in repositories if isinstance(row, dict)])}."
        )
    entrypoint_labels = _entrypoint_labels(entrypoints)
    if entrypoint_labels:
        story.append(f"Public entrypoints: {human_list(entrypoint_labels, limit=5)}.")
    if cloud_resources:
        story.append(
            f"Depends on cloud resources {human_list([str(row.get('name') or '') for row in cloud_resources if isinstance(row, dict)])}."
        )
    if shared_resources:
        story.append(
            f"Shares resources {human_list([str(row.get('name') or '') for row in shared_resources if isinstance(row, dict)])}."
        )
    if dependencies:
        story.append(
            f"Depends on {human_list([str(row.get('name') or '') for row in dependencies if isinstance(row, dict)])}."
        )
    if not story:
        story.append(f"{subject['name']} is available for context lookup.")

    drilldowns = {
        "workload_context": {"workload_id": subject["id"]},
    }
    if subject.get("kind") == "service" or requested_as == "service":
        drilldowns["service_context"] = {"workload_id": subject["id"]}

    gitops_overview = build_gitops_overview(
        deploys_from=list(context.get("deploys_from") or []),
        discovers_config_in=list(context.get("discovers_config_in") or []),
        provisioned_by=list(context.get("provisioned_by") or []),
        delivery_paths=list(context.get("delivery_paths") or []),
        controller_driven_paths=list(context.get("controller_driven_paths") or []),
        deployment_artifacts=dict(context.get("deployment_artifacts") or {}),
        environments=list(context.get("environments") or []),
        observed_config_environments=list(
            context.get("observed_config_environments") or []
        ),
        selected_environment=selected_environment or None,
    )
    if gitops_overview is not None:
        story.append(summarize_gitops_overview(gitops_overview))
    deployment_overview = _build_workload_deployment_overview(
        context=context,
        selected_instance=(
            selected_instance if isinstance(selected_instance, dict) else None
        ),
        instances=instances,
        repositories=repositories,
        entrypoints=entrypoints,
        api_surface=api_surface,
        cloud_resources=cloud_resources,
        shared_resources=shared_resources,
        dependencies=dependencies,
        evidence=evidence,
        requested_as=requested_as,
    )

    story_sections: list[dict[str, Any]] = []
    if selected_instance or instances:
        runtime_summary = (
            f"Selected instance {selected_instance.get('id')}."
            if selected_instance
            else f"{len(instances)} instance candidates are currently known."
        )
        story_sections.append(
            story_section(
                "runtime",
                "Runtime",
                runtime_summary,
                items=[selected_instance] if selected_instance else instances,
            )
        )
    if entrypoint_labels:
        story_sections.append(
            story_section(
                "internet",
                "Internet",
                f"Public entrypoints include {human_list(entrypoint_labels, limit=5)}.",
                items=entrypoints,
            )
        )
    if repositories:
        story_sections.append(
            story_section(
                "repositories",
                "Repositories",
                f"Backed by repositories {human_list([str(row.get('name') or '') for row in repositories if isinstance(row, dict)])}.",
                items=repositories,
            )
        )
    if cloud_resources or shared_resources:
        resource_summary_parts: list[str] = []
        if cloud_resources:
            resource_summary_parts.append(
                f"cloud resources {human_list([str(row.get('name') or '') for row in cloud_resources if isinstance(row, dict)])}"
            )
        if shared_resources:
            resource_summary_parts.append(
                f"shared resources {human_list([str(row.get('name') or '') for row in shared_resources if isinstance(row, dict)])}"
            )
        story_sections.append(
            story_section(
                "resources",
                "Resources",
                "Uses " + " and ".join(resource_summary_parts) + ".",
                items=cloud_resources + shared_resources,
            )
        )
    if dependencies:
        story_sections.append(
            story_section(
                "dependencies",
                "Dependencies",
                f"Depends on {human_list([str(row.get('name') or '') for row in dependencies if isinstance(row, dict)])}.",
                items=dependencies,
            )
        )
    deployment_summary = (
        summarize_gitops_overview(gitops_overview) if gitops_overview else ""
    )
    if deployment_summary:
        story_sections.append(
            story_section(
                "deployment",
                "Deployment",
                deployment_summary,
                items=list(deployment_overview.get("delivery_paths") or [])
                or list(gitops_overview.get("value_layers") or []),
            )
        )
    documentation_overview = build_documentation_overview(
        subject_name=str(subject["name"]),
        subject_type=str(subject.get("type") or "workload"),
        repositories=repositories,
        entrypoints=entrypoints,
        dependencies=dependencies,
        code_overview=None,
        gitops_overview=gitops_overview,
        documentation_evidence=dict(context.get("documentation_evidence") or {}),
        drilldowns=drilldowns,
    )
    support_overview = build_support_overview(
        subject_name=str(subject["name"]),
        instances=[selected_instance] if selected_instance else instances,
        repositories=repositories,
        entrypoints=entrypoints,
        cloud_resources=cloud_resources,
        shared_resources=shared_resources,
        dependencies=dependencies,
        gitops_overview=gitops_overview,
        documentation_overview=documentation_overview,
    )
    if gitops_overview is not None:
        story_sections.append(
            story_section(
                "gitops",
                "GitOps",
                summarize_gitops_overview(gitops_overview),
                items=list(gitops_overview.get("value_layers") or []),
            )
        )
    if documentation_overview is not None:
        story_sections.append(
            story_section(
                "documentation",
                "Documentation",
                summarize_documentation_overview(documentation_overview),
                items=list(documentation_overview.get("key_artifacts") or []),
            )
        )
    if support_overview is not None:
        story_sections.append(
            story_section(
                "support",
                "Support",
                summarize_support_overview(support_overview),
                items=list(support_overview.get("investigation_paths") or []),
            )
        )

    coverage = context.get("coverage")
    limitations = list(context.get("limitations") or [])
    if coverage is None and not limitations:
        limitations.append("coverage_unavailable")

    response = {
        "subject": subject,
        "story": story,
        "story_sections": story_sections,
        "deployment_overview": deployment_overview,
        "gitops_overview": gitops_overview,
        "documentation_overview": documentation_overview,
        "support_overview": support_overview,
        "evidence": evidence,
        "limitations": limitations,
        "coverage": coverage,
        "drilldowns": drilldowns,
    }
    if requested_as:
        response["requested_as"] = requested_as
    return portable_story_value(response)
