"""Repository story contract helpers."""

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
from .story_repository_support import (
    build_repository_deployment_overview,
    dependency_label,
    focused_deployment_story,
    subject_from_repository,
)
from .story_shared import human_list, portable_story_value, story_section
from .story_support import build_support_overview, summarize_support_overview


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

    deployment_overview = build_repository_deployment_overview(context)
    controller_overview = build_controller_overview(
        delivery_paths=list(deployment_overview.get("delivery_paths") or []),
        controller_driven_paths=list(
            deployment_overview.get("controller_driven_paths") or []
        ),
    )
    runtime_overview = build_runtime_overview(
        selected_instance=None,
        instances=[],
        entrypoints=hostnames,
        platforms=list(deployment_overview.get("runtime_platforms") or []),
        observed_config_environments=list(
            deployment_overview.get("observed_config_environments") or []
        ),
    )
    deployment_facts = build_deployment_facts(
        delivery_paths=list(deployment_overview.get("delivery_paths") or []),
        controller_driven_paths=list(
            deployment_overview.get("controller_driven_paths") or []
        ),
        platforms=list(deployment_overview.get("runtime_platforms") or []),
        entrypoints=hostnames,
        observed_config_environments=list(
            deployment_overview.get("observed_config_environments") or []
        ),
    )
    deployment_fact_summary = build_deployment_fact_summary(
        delivery_paths=list(deployment_overview.get("delivery_paths") or []),
        controller_driven_paths=list(
            deployment_overview.get("controller_driven_paths") or []
        ),
        platforms=list(deployment_overview.get("runtime_platforms") or []),
        entrypoints=hostnames,
        observed_config_environments=list(
            deployment_overview.get("observed_config_environments") or []
        ),
    )
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
        api_surface=api_surface,
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
            *[
                {"name": dependency_label(row)}
                for row in dependencies
                if dependency_label(row)
            ],
        ],
        consumer_repositories=consumer_repositories,
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
            "controller_overview": controller_overview,
            "runtime_overview": runtime_overview,
            "deployment_facts": deployment_facts,
            "deployment_fact_summary": deployment_fact_summary,
            "code_overview": code_overview,
            "evidence": evidence,
            "limitations": limitations,
            "coverage": context.get("coverage"),
            "drilldowns": drilldowns,
        }
    )
