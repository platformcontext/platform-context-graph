"""Support- and runbook-focused shaping helpers for story responses."""

from __future__ import annotations

from typing import Any

from .story_shared import human_list


def _dependency_name(row: dict[str, Any]) -> str:
    """Return a human-friendly dependency label."""

    return str(
        row.get("name")
        or row.get("repository")
        or row.get("repo_slug")
        or row.get("hostname")
        or ""
    ).strip()


def build_support_overview(
    *,
    subject_name: str,
    instances: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    cloud_resources: list[dict[str, Any]],
    shared_resources: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    consumer_repositories: list[dict[str, Any]] | None = None,
    gitops_overview: dict[str, Any] | None,
    documentation_overview: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a support/runbook overview from story and content evidence."""

    key_artifacts = list((documentation_overview or {}).get("key_artifacts") or [])
    consumer_repositories = list(consumer_repositories or [])
    if not any(
        [
            instances,
            repositories,
            entrypoints,
            cloud_resources,
            shared_resources,
            dependencies,
            consumer_repositories,
            gitops_overview,
            key_artifacts,
        ]
    ):
        return None

    runtime_components = [row for row in instances if isinstance(row, dict)]
    if not runtime_components:
        runtime_components = [row for row in repositories if isinstance(row, dict)]

    dependency_hotspots = [
        {
            "name": _dependency_name(row),
            "type": row.get("type") or row.get("kind") or "dependency",
        }
        for row in [*cloud_resources, *shared_resources, *dependencies]
        if isinstance(row, dict) and _dependency_name(row)
    ]

    investigation_paths: list[dict[str, Any]] = []
    entrypoint_labels = [
        _dependency_name(row) for row in entrypoints if isinstance(row, dict)
    ]
    if entrypoint_labels:
        investigation_paths.append(
            {
                "topic": "request_failures",
                "summary": (
                    f"Start with {human_list(entrypoint_labels, limit=5)} and then confirm runtime and routing evidence."
                ),
                "artifacts": key_artifacts[:3],
            }
        )
    if gitops_overview and (gitops_overview.get("value_layers") or key_artifacts):
        controllers = [
            str(value)
            for value in (gitops_overview.get("owner") or {}).get(
                "delivery_controllers"
            )
            or []
            if str(value).strip()
        ]
        investigation_paths.append(
            {
                "topic": "deploy_and_config",
                "summary": (
                    "Inspect GitOps values, overlays, and deployment controllers"
                    + (
                        f" routed through {human_list(controllers)}."
                        if controllers
                        else "."
                    )
                ),
                "artifacts": key_artifacts[:5],
            }
        )
    if dependency_hotspots:
        investigation_paths.append(
            {
                "topic": "dependency_failures",
                "summary": (
                    f"Check shared dependencies such as {human_list([row['name'] for row in dependency_hotspots], limit=4)}."
                ),
                "artifacts": key_artifacts[:4],
            }
        )
    if consumer_repositories:
        consumer_names = [
            str(row.get("repository") or row.get("name") or "").strip()
            for row in consumer_repositories
            if isinstance(row, dict)
            and str(row.get("repository") or row.get("name") or "").strip()
        ]
        if consumer_names:
            investigation_paths.append(
                {
                    "topic": "consumer_impact",
                    "summary": (
                        "Check downstream consumer impact across "
                        f"{human_list(consumer_names, limit=4)}."
                    ),
                    "artifacts": key_artifacts[:3],
                }
            )

    return {
        "runtime_components": runtime_components,
        "entrypoints": entrypoints,
        "dependency_hotspots": dependency_hotspots,
        "consumer_repositories": consumer_repositories,
        "investigation_paths": investigation_paths,
        "key_artifacts": key_artifacts,
        "limitations": ([] if key_artifacts else ["support_artifacts_missing"]),
    }


def summarize_support_overview(support_overview: dict[str, Any]) -> str:
    """Return a concise support section summary."""

    paths = support_overview.get("investigation_paths") or []
    topics = [
        str(row.get("topic") or "").replace("_", " ")
        for row in paths
        if isinstance(row, dict) and str(row.get("topic") or "").strip()
    ]
    if topics:
        return "Support investigation starts with " + human_list(topics, limit=3) + "."
    return "Support-focused evidence is available for this story."
