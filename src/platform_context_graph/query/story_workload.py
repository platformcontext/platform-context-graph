"""Workload and service story contract helpers."""

from __future__ import annotations

from typing import Any

from .story_deployment_mapping import build_controller_overview
from .story_deployment_mapping import build_deployment_fact_summary
from .story_deployment_mapping import build_deployment_facts
from .story_deployment_mapping import build_runtime_overview
from .story_documentation import (
    build_documentation_overview,
    summarize_documentation_overview,
)
from .story_gitops import build_gitops_overview, summarize_gitops_overview
from .story_shared import human_list, portable_story_value, story_section
from .story_support import build_support_overview, summarize_support_overview
from .story_workload_support import (
    api_surface_entrypoints,
    build_workload_investigation_hints,
    build_workload_deployment_overview,
    entrypoint_labels as build_entrypoint_labels,
    public_entrypoint_labels as build_public_entrypoint_labels,
    rank_entrypoints,
    selected_environment_for_story,
)


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
    platforms = list(context.get("platforms") or [])
    delivery_paths = list(context.get("delivery_paths") or [])
    controller_driven_paths = list(context.get("controller_driven_paths") or [])
    observed_config_environments = list(
        context.get("observed_config_environments") or []
    )
    selected_environment = selected_environment_for_story(
        selected_instance=selected_instance,
        context=context,
        entrypoints=list(context.get("entrypoints") or []),
    )
    entrypoints = rank_entrypoints(
        [
            *list(context.get("entrypoints") or []),
            *api_surface_entrypoints(api_surface),
        ],
        selected_environment=selected_environment,
    )
    evidence = list(context.get("evidence") or [])
    requested_as = context.get("requested_as")
    controller_overview = build_controller_overview(
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
    )
    runtime_overview = build_runtime_overview(
        selected_instance=(
            selected_instance if isinstance(selected_instance, dict) else None
        ),
        instances=instances,
        entrypoints=entrypoints,
        platforms=platforms,
        observed_config_environments=observed_config_environments,
    )
    deployment_facts = build_deployment_facts(
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
        platforms=platforms,
        entrypoints=entrypoints,
        observed_config_environments=observed_config_environments,
    )
    deployment_fact_summary = build_deployment_fact_summary(
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
        platforms=platforms,
        entrypoints=entrypoints,
        observed_config_environments=observed_config_environments,
    )

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
    entrypoint_labels = build_entrypoint_labels(entrypoints)
    public_entrypoint_labels = build_public_entrypoint_labels(entrypoints)
    if public_entrypoint_labels:
        story.append(
            f"Public entrypoints: {human_list(public_entrypoint_labels, limit=5)}."
        )
    elif entrypoint_labels:
        story.append(f"Known entrypoints: {human_list(entrypoint_labels, limit=5)}.")
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
    investigation_hints = build_workload_investigation_hints(
        subject=subject,
        selected_environment=selected_environment,
        deploys_from=list(context.get("deploys_from") or []),
        provisioned_by=list(context.get("provisioned_by") or []),
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
    )
    if investigation_hints is not None:
        drilldowns["investigation_hints"] = investigation_hints

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
    deployment_overview = build_workload_deployment_overview(
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
    if public_entrypoint_labels:
        story_sections.append(
            story_section(
                "internet",
                "Internet",
                (
                    f"Public entrypoints include "
                    f"{human_list(public_entrypoint_labels, limit=5)}."
                ),
                items=entrypoints,
            )
        )
    elif entrypoint_labels:
        story_sections.append(
            story_section(
                "internet",
                "Internet",
                f"Known entrypoints include {human_list(entrypoint_labels, limit=5)}.",
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
        api_surface=api_surface,
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
        consumer_repositories=list(context.get("consumer_repositories") or []),
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
        "controller_overview": controller_overview,
        "runtime_overview": runtime_overview,
        "deployment_facts": deployment_facts,
        "deployment_fact_summary": deployment_fact_summary,
        "evidence": evidence,
        "limitations": limitations,
        "coverage": coverage,
        "drilldowns": drilldowns,
    }
    if requested_as:
        response["requested_as"] = requested_as
    return portable_story_value(response)
