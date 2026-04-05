"""Repository story contract helpers."""

from __future__ import annotations

from typing import Any

from .story_documentation import (
    build_documentation_overview,
    summarize_documentation_overview,
)
from .story_gitops import build_gitops_overview, summarize_gitops_overview
from .story_repository_support import (
    dependency_label,
    focused_deployment_story,
    subject_from_repository,
)
from .story_shared import human_list, portable_story_value, story_section
from .story_support import build_support_overview, summarize_support_overview


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


def build_repository_story_response(
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build the structured story contract for one repository."""

    subject = subject_from_repository(context)
    code = context.get("code") or {}
    hostnames = list(context.get("hostnames") or [])
    api_surface = dict(context.get("api_surface") or {})
    consumer_repositories = list(context.get("consumer_repositories") or [])
    deploys_from = list(context.get("deploys_from") or [])
    dependencies = list((context.get("ecosystem") or {}).get("dependencies") or [])
    limitations = list(context.get("limitations") or [])

    deployment_overview = _build_repository_deployment_overview(context)
    deployment_story = list(deployment_overview.get("deployment_story") or [])
    direct_story = focused_deployment_story(deployment_story)
    if direct_story:
        deployment_overview["direct_story"] = direct_story
        deployment_overview["trace_controls"] = {
            "direct_only": True,
            "include_shared_config": False,
            "include_consumers": False,
        }
        omitted_sections = []
        if deployment_overview.get("deployment_artifacts"):
            config_paths = list(
                (deployment_overview.get("deployment_artifacts") or {}).get(
                    "config_paths"
                )
                or []
            )
            if config_paths:
                omitted_sections.append("shared_config_paths")
        if deployment_overview.get("consumer_repositories"):
            omitted_sections.append("consumer_repositories")
        if omitted_sections:
            deployment_overview["trace_limitations"] = {
                "omitted_sections": omitted_sections,
                "reason": (
                    "Keep the repository story focused on direct deployment evidence."
                ),
            }
    story = list(direct_story or deployment_overview.get("topology_story") or [])
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
            details.append(f"entrypoints {human_list(public_hostnames)}")
        if api_surface.get("api_versions"):
            details.append(
                f"versions {human_list([str(v) for v in api_surface.get('api_versions') or []])}"
            )
        if api_surface.get("docs_routes"):
            details.append(
                f"docs {human_list([str(v) for v in api_surface.get('docs_routes') or []])}"
            )
        story_sections.append(
            story_section(
                "internet",
                "Internet",
                "API surface exposes " + " and ".join(details) + ".",
                items=hostnames,
            )
        )

    deployment_summary = (
        direct_story
        or deployment_overview.get("topology_story")
        or deployment_overview.get("deployment_story")
    )
    if deployment_summary:
        story_sections.append(
            story_section(
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
    drilldowns = {
        "repo_context": {"repo_id": subject["id"]},
        "repo_summary": {"repo_name": subject["name"]},
        "deployment_chain": {"service_name": subject["name"]},
    }

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
    )
    documentation_overview = build_documentation_overview(
        subject_name=str(subject["name"]),
        subject_type="repository",
        repositories=[subject],
        entrypoints=hostnames,
        dependencies=[
            *deploys_from,
            *consumer_repositories,
            *[
                {"name": dependency_label(row)}
                for row in dependencies
                if dependency_label(row)
            ],
        ],
        code_overview=code_overview,
        gitops_overview=gitops_overview,
        documentation_evidence=dict(context.get("documentation_evidence") or {}),
        drilldowns=drilldowns,
    )
    support_overview = build_support_overview(
        subject_name=str(subject["name"]),
        instances=[],
        repositories=[subject],
        entrypoints=hostnames,
        cloud_resources=[],
        shared_resources=[],
        dependencies=[
            *deploys_from,
            *consumer_repositories,
            *[
                {"name": dependency_label(row)}
                for row in dependencies
                if dependency_label(row)
            ],
        ],
        gitops_overview=gitops_overview,
        documentation_overview=documentation_overview,
    )
    story_sections.append(
        story_section(
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
        dependency_items: list[dict[str, Any]] = list(deploys_from) + list(
            consumer_repositories
        )
        if deploys_from:
            deploy_sources = [
                str(row.get("name") or "").strip()
                for row in deploys_from
                if isinstance(row, dict) and str(row.get("name") or "").strip()
            ]
            if deploy_sources:
                dependency_summary_parts.append(
                    f"deploys from {human_list(deploy_sources)}"
                )
        if consumer_repositories:
            consumer_names = [
                str(row.get("repository") or row.get("name") or "").strip()
                for row in consumer_repositories
                if isinstance(row, dict)
                and str(row.get("repository") or row.get("name") or "").strip()
            ]
            if consumer_names:
                dependency_summary_parts.append(
                    f"has consumers {human_list(consumer_names)}"
                )
        if dependencies:
            dependency_names = [
                label
                for label in (dependency_label(row) for row in dependencies)
                if label
            ]
            if dependency_names:
                dependency_summary_parts.append(
                    f"depends on {human_list(dependency_names)}"
                )
                dependency_items.extend(
                    [
                        {"type": "repository", "name": label}
                        for label in dependency_names
                    ]
                )
        if dependency_summary_parts:
            story_sections.append(
                story_section(
                    "dependencies",
                    "Dependencies",
                    " and ".join(dependency_summary_parts).capitalize() + ".",
                    items=dependency_items,
                )
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

    return portable_story_value(
        {
            "subject": subject,
            "story": story,
            "story_sections": story_sections,
            "deployment_overview": deployment_overview or None,
            "gitops_overview": gitops_overview,
            "documentation_overview": documentation_overview,
            "support_overview": support_overview,
            "code_overview": code_overview,
            "evidence": evidence,
            "limitations": limitations,
            "coverage": context.get("coverage"),
            "drilldowns": drilldowns,
        }
    )
