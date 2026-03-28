"""Workload and service story contract helpers."""

from __future__ import annotations

from typing import Any

from .story_shared import human_list, portable_story_value, story_section


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
            f"Depends on workloads {human_list([str(row.get('name') or '') for row in dependencies if isinstance(row, dict)])}."
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

    response = {
        "subject": subject,
        "story": story,
        "story_sections": story_sections,
        "deployment_overview": deployment_overview,
        "evidence": evidence,
        "limitations": [],
        "coverage": None,
        "drilldowns": drilldowns,
    }
    if requested_as:
        response["requested_as"] = requested_as
    return portable_story_value(response)
