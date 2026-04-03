"""Story-shaping helpers for high-level ecosystem deployment overviews."""

from typing import Any


def build_topology_story(
    *,
    hostnames: list[dict[str, Any]],
    api_surface: dict[str, Any],
    deployment_story: list[str],
    gateways: list[dict[str, Any]],
    service_ports: list[dict[str, Any]],
    shared_config_paths: list[dict[str, Any]],
    consumer_repositories: list[dict[str, Any]],
) -> list[str]:
    """Build a compact internet-to-cloud-to-code narrative from derived facts."""

    lines: list[str] = []
    public_hostnames = [
        str(row.get("hostname") or "").strip()
        for row in hostnames
        if isinstance(row, dict) and str(row.get("hostname") or "").strip()
    ]
    if public_hostnames:
        lines.append(f"Public entrypoints: {', '.join(public_hostnames)}.")

    api_versions = [
        str(value).strip()
        for value in api_surface.get("api_versions") or []
        if str(value).strip()
    ]
    docs_routes = [
        str(value).strip()
        for value in api_surface.get("docs_routes") or []
        if str(value).strip()
    ]
    if api_versions or docs_routes:
        details: list[str] = []
        if api_versions:
            details.append(f"versions {', '.join(api_versions)}")
        if docs_routes:
            details.append(f"docs routes {', '.join(docs_routes)}")
        lines.append(f"API surface exposes {' and '.join(details)}.")

    lines.extend(deployment_story)
    access_story = build_network_access_story(
        gateways=gateways,
        service_ports=service_ports,
    )
    if access_story:
        lines.append(access_story)
    shared_config_story = build_shared_config_story(shared_config_paths)
    if shared_config_story:
        lines.append(shared_config_story)
    consumer_story = build_consumer_story(consumer_repositories)
    if consumer_story:
        lines.append(consumer_story)

    return lines


def build_deployment_story_fallback(
    *,
    runtime_platforms: list[dict[str, Any]],
    deployment_controllers: list[str],
    service_variants: list[dict[str, Any]],
) -> list[str]:
    """Return a fallback deployment story when workflow paths are unavailable."""

    if not deployment_controllers:
        return []
    controller_summary = _human_join(
        [str(value).strip() for value in deployment_controllers]
    )
    if not controller_summary:
        return []
    variant_names = _human_join(
        [
            str(row.get("name") or "").strip()
            for row in service_variants
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ]
    )
    platform_summary = _runtime_platform_summary(runtime_platforms)

    line = f"Deployment controllers {controller_summary} manage"
    if variant_names:
        line += f" variants {variant_names}"
    else:
        line += " this service"
    if platform_summary:
        line += f" on {platform_summary}"
    return [line + "."]


def build_controller_driven_story(
    *,
    controller_driven_paths: list[dict[str, Any]],
) -> list[str]:
    """Return a compact deployment story from controller-driven automation paths."""

    lines: list[str] = []
    seen: set[str] = set()
    for row in controller_driven_paths:
        if not isinstance(row, dict):
            continue
        controller = _controller_label(str(row.get("controller_kind") or ""))
        automation_kind = _automation_label(str(row.get("automation_kind") or ""))
        entry_points = [
            str(value).strip()
            for value in row.get("entry_points") or []
            if str(value).strip()
        ]
        target_descriptors = [
            str(value).strip()
            for value in row.get("target_descriptors") or []
            if str(value).strip()
        ]
        runtime_family = _runtime_family_label(str(row.get("runtime_family") or ""))
        supporting_repositories = [
            str(value).strip()
            for value in row.get("supporting_repositories") or []
            if str(value).strip()
        ]

        if not entry_points:
            continue

        line = (
            f"{controller} invokes {automation_kind} entry points "
            f"{_human_join(entry_points)}"
        )
        if target_descriptors:
            line += f" targeting {_human_join(target_descriptors)}"
        if runtime_family:
            line += f" for {runtime_family}"
        if supporting_repositories:
            line += f" with support from {_human_join(supporting_repositories)}"
        line += "."
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def build_network_access_story(
    *,
    gateways: list[dict[str, Any]],
    service_ports: list[dict[str, Any]],
) -> str:
    """Return one line describing ingress gateways and service ports."""

    gateway_names = limited_list(
        [
            str(row.get("name") or "").strip()
            for row in gateways
            if isinstance(row, dict) and str(row.get("name") or "").strip()
        ],
        2,
    )
    port_values = limited_list(
        [
            str(row.get("port") or "").strip()
            for row in service_ports
            if isinstance(row, dict) and str(row.get("port") or "").strip()
        ],
        3,
    )
    if not gateway_names and not port_values:
        return ""
    if gateway_names and port_values:
        return (
            f"Traffic enters through gateways {gateway_names} on service ports "
            f"{port_values}."
        )
    if gateway_names:
        return f"Traffic enters through gateways {gateway_names}."
    return f"Service traffic listens on ports {port_values}."


def _runtime_platform_summary(runtime_platforms: list[dict[str, Any]]) -> str:
    """Return a compact runtime-platform summary for story fallback lines."""

    rendered: list[str] = []
    for row in runtime_platforms:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        environment = str(row.get("environment") or "").strip()
        if not kind:
            continue
        detail = kind
        if name:
            detail += f" {name}"
        if environment:
            detail += f" in {environment}"
        rendered.append(detail)
    return _human_join(rendered)


def _automation_label(value: str) -> str:
    """Return a display label for one automation family."""

    normalized = value.strip().lower()
    if normalized == "ansible":
        return "Ansible"
    return value.replace("_", " ").strip() or "automation"


def _runtime_family_label(value: str) -> str:
    """Return a display label for one automation runtime family."""

    normalized = value.strip().lower()
    labels = {
        "wordpress_website_fleet": "wordpress website fleets",
        "php_web_platform": "PHP web platforms",
        "ecs_service": "ECS services",
        "kubernetes_gitops": "Kubernetes GitOps workloads",
    }
    if normalized in labels:
        return labels[normalized]
    return value.replace("_", " ").strip()


def _controller_label(value: str) -> str:
    """Return a display label for one deployment controller."""

    normalized = value.strip().lower()
    if normalized == "github_actions":
        return "GitHub Actions"
    if normalized == "jenkins":
        return "Jenkins"
    return value.replace("_", " ").strip() or "Unknown controller"


def _human_join(values: list[str]) -> str:
    """Return a human-readable conjunction for one or more strings."""

    ordered = [value for value in values if value]
    if not ordered:
        return ""
    if len(ordered) == 1:
        return ordered[0]
    if len(ordered) == 2:
        return f"{ordered[0]} and {ordered[1]}"
    return f"{', '.join(ordered[:-1])}, and {ordered[-1]}"


def build_shared_config_story(rows: list[dict[str, Any]]) -> str:
    """Return one ranked, truncated shared-config story line."""

    grouped: dict[tuple[str, ...], list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        source_repositories = tuple(
            str(value).strip()
            for value in row.get("source_repositories") or []
            if str(value).strip()
        )
        if not path or not source_repositories:
            continue
        grouped.setdefault(source_repositories, []).append(path)

    ranked_groups = sorted(
        grouped.items(),
        key=lambda item: (-len(item[0]), -len(item[1]), item[0]),
    )
    parts: list[str] = []
    shown_groups = 0
    for source_repositories, paths in ranked_groups[:2]:
        unique_paths = sorted(dict.fromkeys(paths))
        path_summary = limited_list(unique_paths, 2)
        repo_summary = limited_list(list(source_repositories), 3)
        parts.append(f"{repo_summary}: {path_summary}")
        shown_groups += 1
    if not parts:
        return ""
    extra_groups = len(ranked_groups) - shown_groups
    suffix = f"; and {extra_groups} more" if extra_groups > 0 else ""
    return f"Shared config families span {'; and '.join(parts)}{suffix}."


def build_consumer_story(rows: list[dict[str, Any]]) -> str:
    """Return one ranked consumer-only story line."""

    ranked = sorted(
        [
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("repository") or "").strip()
        ],
        key=_consumer_rank_key,
    )
    if not ranked:
        return ""
    if len(ranked) == 1:
        row = ranked[0]
        repo = str(row.get("repository") or "").strip()
        evidence = _consumer_evidence_label(row)
        sample_path = str((row.get("sample_paths") or [""])[0]).strip()
        suffix = f" in {sample_path}" if evidence and sample_path else ""
        if evidence:
            return (
                f"Consumer-only repository {repo} references this service via "
                f"{evidence}{suffix}."
            )
        return f"Consumer-only repository {repo} references this service."
    top_row = ranked[0]
    top_repo = str(top_row.get("repository") or "").strip()
    top_evidence = _consumer_evidence_label(top_row)
    top_sample_path = str((top_row.get("sample_paths") or [""])[0]).strip()
    leading = f"Top consumer-only repository {top_repo} references this service"
    if top_evidence:
        leading += f" via {top_evidence}"
    if top_sample_path:
        leading += f" in {top_sample_path}"
    remaining = [row.get("repository") for row in ranked[1:]]
    if not remaining:
        return leading + "."
    return f"{leading}. Additional consumers: {limited_list(remaining, 2)}."


def limited_list(values: list[Any], limit: int) -> str:
    """Return an ordered, truncated comma-separated list."""

    ordered = [str(value).strip() for value in values if str(value).strip()]
    if len(ordered) <= limit:
        return ", ".join(ordered)
    shown = ", ".join(ordered[:limit])
    return f"{shown}, and {len(ordered) - limit} more"


def _consumer_rank_key(row: dict[str, Any]) -> tuple[int, int]:
    """Return a stable rank key for one consumer-only repository row."""

    evidence_kind = str((row.get("evidence_kinds") or [""])[0]).strip()
    evidence_rank = {
        "hostname_reference": 0,
        "config_path_reference": 1,
        "repository_reference": 2,
    }.get(evidence_kind, 3)
    has_sample_path = 0 if (row.get("sample_paths") or []) else 1
    return (evidence_rank, has_sample_path)


def _consumer_evidence_label(row: dict[str, Any]) -> str:
    """Return a human-readable evidence label for one consumer row."""

    kind = str((row.get("evidence_kinds") or [""])[0]).strip()
    return {
        "hostname_reference": "hostname references",
        "config_path_reference": "config path references",
        "repository_reference": "repository references",
    }.get(kind, kind.replace("_", " ").strip())


__all__ = [
    "build_consumer_story",
    "build_controller_driven_story",
    "build_deployment_story_fallback",
    "build_network_access_story",
    "build_shared_config_story",
    "build_topology_story",
    "limited_list",
]
