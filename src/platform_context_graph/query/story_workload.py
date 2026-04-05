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
    entrypoints = list(context.get("entrypoints") or [])
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

    deployment_overview = {
        "instances": [selected_instance] if selected_instance else instances,
        "repositories": repositories,
        "entrypoints": entrypoints,
        "cloud_resources": cloud_resources,
        "shared_resources": shared_resources,
        "dependencies": dependencies,
        "evidence": evidence,
        **({"requested_as": requested_as} if requested_as else {}),
    }

    drilldowns = {
        "workload_context": {"workload_id": subject["id"]},
    }
    if subject.get("kind") == "service" or requested_as == "service":
        drilldowns["service_context"] = {"workload_id": subject["id"]}

    selected_environment = None
    if isinstance(selected_instance, dict):
        selected_environment = str(selected_instance.get("environment") or "").strip()
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
