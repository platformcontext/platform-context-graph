"""Shared story-contract helpers for repository and workload narratives."""

from __future__ import annotations

from typing import Any


def _story_section(
    section_id: str,
    title: str,
    summary: str,
    *,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return one structured story section."""

    return {
        "id": section_id,
        "title": title,
        "summary": summary,
        "items": list(items or []),
    }


def _human_list(values: list[str], *, limit: int = 3) -> str:
    """Return a short human-readable list summary."""

    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    shown = ", ".join(cleaned[:limit])
    return f"{shown}, and {len(cleaned) - limit} more"


def _portable_story_value(value: Any) -> Any:
    """Strip server-local path details from story payloads."""

    if isinstance(value, list):
        return [_portable_story_value(item) for item in value]
    if not isinstance(value, dict):
        return value

    entity_type = value.get("type")
    has_relative_path = isinstance(value.get("relative_path"), str)
    portable: dict[str, Any] = {}
    for key, item in value.items():
        if key == "local_path":
            continue
        if key == "path" and (
            entity_type == "repository"
            or has_relative_path
            or (isinstance(item, str) and item.startswith("/"))
        ):
            continue
        portable[key] = _portable_story_value(item)
    return portable


def _subject_from_repository(context: dict[str, Any]) -> dict[str, Any]:
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


def _build_repository_deployment_overview(
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact deployment overview without depending on MCP modules."""

    hostnames = list(context.get("hostnames") or [])
    api_surface = dict(context.get("api_surface") or {})
    platforms = list(context.get("platforms") or [])
    delivery_paths = list(context.get("delivery_paths") or [])
    controller_driven_paths = list(context.get("controller_driven_paths") or [])
    deployment_artifacts = dict(context.get("deployment_artifacts") or {})
    consumer_repositories = list(context.get("consumer_repositories") or [])
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
            f"Public entrypoints: {_human_list(public_hostnames, limit=5)}."
        )
    if api_surface.get("api_versions") or api_surface.get("docs_routes"):
        api_parts: list[str] = []
        versions = [str(v) for v in api_surface.get("api_versions") or [] if str(v)]
        docs_routes = [str(v) for v in api_surface.get("docs_routes") or [] if str(v)]
        if versions:
            api_parts.append(f"versions {_human_list(versions)}")
        if docs_routes:
            api_parts.append(f"docs {_human_list(docs_routes)}")
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
            parts.append(f"from {_human_list(deployment_sources)}")
        if platform_kinds:
            parts.append(f"onto {_human_list(platform_kinds)}")
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
            parts.append(f"via {_human_list(entry_points)}")
        if parts:
            deployment_story.append(
                "Controller-driven delivery uses " + " ".join(parts) + "."
            )

    topology_story = list(deployment_story)
    if deployment_artifacts.get("config_paths"):
        topology_story.append(
            "Shared config paths include "
            + _human_list(
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
            + _human_list(
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
        "internet_entrypoints": public_hostnames,
        "internal_entrypoints": internal_hostnames,
        "api_surface": {
            "docs_routes": list(api_surface.get("docs_routes") or []),
            "api_versions": list(api_surface.get("api_versions") or []),
        },
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
        "delivery_paths": delivery_paths,
        "controller_driven_paths": controller_driven_paths,
        "deployment_artifacts": deployment_artifacts or None,
        "consumer_repositories": consumer_repositories,
        "deployment_story": deployment_story,
        "topology_story": topology_story,
    }


def build_repository_story_response(
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build the structured story contract for one repository."""

    subject = _subject_from_repository(context)
    code = context.get("code") or {}
    hostnames = list(context.get("hostnames") or [])
    api_surface = dict(context.get("api_surface") or {})
    deployment_artifacts = dict(context.get("deployment_artifacts") or {})
    consumer_repositories = list(context.get("consumer_repositories") or [])
    deploys_from = list(context.get("deploys_from") or [])
    dependencies = list((context.get("ecosystem") or {}).get("dependencies") or [])
    limitations = list(context.get("limitations") or [])

    deployment_overview = _build_repository_deployment_overview(context)
    story = list(deployment_overview.get("topology_story") or [])
    if not story:
        story = [
            f"{subject['name']} contains "
            f"{code.get('functions', 0)} functions and {code.get('classes', 0)} classes."
        ]

    story_sections: list[dict[str, Any]] = []
    public_hostnames = [
        str(row.get("hostname") or "").strip()
        for row in hostnames
        if isinstance(row, dict) and str(row.get("hostname") or "").strip()
    ]
    if public_hostnames or api_surface:
        details: list[str] = []
        if public_hostnames:
            details.append(f"entrypoints { _human_list(public_hostnames) }")
        if api_surface.get("api_versions"):
            details.append(
                f"versions {_human_list([str(v) for v in api_surface.get('api_versions') or []])}"
            )
        if api_surface.get("docs_routes"):
            details.append(
                f"docs {_human_list([str(v) for v in api_surface.get('docs_routes') or []])}"
            )
        story_sections.append(
            _story_section(
                "internet",
                "Internet",
                "API surface exposes " + " and ".join(details) + ".",
                items=hostnames,
            )
        )

    deployment_summary = deployment_overview.get(
        "topology_story"
    ) or deployment_overview.get("deployment_story")
    if deployment_summary:
        story_sections.append(
            _story_section(
                "deployment",
                "Deployment",
                " ".join(str(value) for value in deployment_summary),
                items=list(deployment_overview.get("delivery_paths") or [])
                or list(deployment_overview.get("controller_driven_paths") or []),
            )
        )

    code_overview = {
        "file_count": context.get("repository", {}).get("discovered_file_count")
        or context.get("repository", {}).get("file_count")
        or 0,
        "functions": int(code.get("functions") or 0),
        "classes": int(code.get("classes") or 0),
        "class_methods": int(code.get("class_methods") or 0),
    }
    story_sections.append(
        _story_section(
            "code",
            "Code",
            (
                f"Repository contains {code_overview['functions']} functions, "
                f"{code_overview['classes']} classes, and "
                f"{code_overview['file_count']} discovered files."
            ),
        )
    )

    if deploys_from or consumer_repositories or dependencies:
        dependency_summary_parts: list[str] = []
        if deploys_from:
            dependency_summary_parts.append(
                f"deploys from {_human_list([str(row.get('name') or '') for row in deploys_from if isinstance(row, dict)])}"
            )
        if consumer_repositories:
            dependency_summary_parts.append(
                f"has consumers {_human_list([str(row.get('repository') or row.get('name') or '') for row in consumer_repositories if isinstance(row, dict)])}"
            )
        if dependencies:
            dependency_summary_parts.append(
                f"depends on {_human_list([str(row.get('name') or '') for row in dependencies if isinstance(row, dict)])}"
            )
        story_sections.append(
            _story_section(
                "dependencies",
                "Dependencies",
                " and ".join(dependency_summary_parts).capitalize() + ".",
                items=deploys_from + consumer_repositories,
            )
        )

    evidence: list[dict[str, Any]] = []
    for hostname in public_hostnames[:3]:
        evidence.append({"source": "hostnames", "detail": hostname, "weight": 1.0})
    for row in deploys_from[:3]:
        if isinstance(row, dict) and row.get("name"):
            evidence.append(
                {
                    "source": "deploys_from",
                    "detail": str(row.get("name")),
                    "weight": 0.8,
                }
            )
    for row in consumer_repositories[:3]:
        if isinstance(row, dict) and (row.get("repository") or row.get("name")):
            evidence.append(
                {
                    "source": "consumer_repositories",
                    "detail": str(row.get("repository") or row.get("name")),
                    "weight": 0.6,
                }
            )

    return _portable_story_value(
        {
        "subject": subject,
        "story": story,
        "story_sections": story_sections,
        "deployment_overview": deployment_overview or None,
        "code_overview": code_overview,
        "evidence": evidence,
        "limitations": limitations,
        "coverage": context.get("coverage"),
        "drilldowns": {
            "repo_context": {"repo_id": subject["id"]},
            "repo_summary": {"repo_name": subject["name"]},
            "deployment_chain": {"service_name": subject["name"]},
        },
        }
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
            f"Owned by repositories {_human_list([str(row.get('name') or '') for row in repositories if isinstance(row, dict)])}."
        )
    if cloud_resources:
        story.append(
            f"Depends on cloud resources {_human_list([str(row.get('name') or '') for row in cloud_resources if isinstance(row, dict)])}."
        )
    if shared_resources:
        story.append(
            f"Shares resources {_human_list([str(row.get('name') or '') for row in shared_resources if isinstance(row, dict)])}."
        )
    if dependencies:
        story.append(
            f"Depends on workloads {_human_list([str(row.get('name') or '') for row in dependencies if isinstance(row, dict)])}."
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
            _story_section(
                "runtime",
                "Runtime",
                runtime_summary,
                items=[selected_instance] if selected_instance else instances,
            )
        )
    if repositories:
        story_sections.append(
            _story_section(
                "repositories",
                "Repositories",
                f"Backed by repositories {_human_list([str(row.get('name') or '') for row in repositories if isinstance(row, dict)])}.",
                items=repositories,
            )
        )
    if cloud_resources or shared_resources:
        resource_summary_parts: list[str] = []
        if cloud_resources:
            resource_summary_parts.append(
                f"cloud resources {_human_list([str(row.get('name') or '') for row in cloud_resources if isinstance(row, dict)])}"
            )
        if shared_resources:
            resource_summary_parts.append(
                f"shared resources {_human_list([str(row.get('name') or '') for row in shared_resources if isinstance(row, dict)])}"
            )
        story_sections.append(
            _story_section(
                "resources",
                "Resources",
                "Uses " + " and ".join(resource_summary_parts) + ".",
                items=cloud_resources + shared_resources,
            )
        )
    if dependencies:
        story_sections.append(
            _story_section(
                "dependencies",
                "Dependencies",
                f"Depends on {_human_list([str(row.get('name') or '') for row in dependencies if isinstance(row, dict)])}.",
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
    return _portable_story_value(response)
