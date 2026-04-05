"""Support helpers for workload and service story shaping."""

from __future__ import annotations

from typing import Any


def normalize_environment(value: Any) -> str:
    """Return a normalized environment token for story comparisons."""

    return str(value or "").strip().lower()


def entrypoint_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    """Return a stable identity tuple for one entrypoint row."""

    return (
        str(row.get("hostname") or "").strip(),
        str(row.get("path") or "").strip(),
        str(row.get("relative_path") or "").strip(),
    )


def api_surface_entrypoints(api_surface: dict[str, Any]) -> list[dict[str, Any]]:
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


def entrypoint_sort_key(
    row: dict[str, Any], *, selected_environment: str | None
) -> tuple[int, int, str]:
    """Return a stable ranking for story entrypoints.

    Public hostnames for the selected environment rank highest, followed by
    health and status endpoints, docs routes, internal hostnames, and then
    generic API paths.
    """

    normalized_selected_environment = normalize_environment(selected_environment)
    normalized_row_environment = normalize_environment(row.get("environment"))
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


def rank_entrypoints(
    entrypoints: list[dict[str, Any]], *, selected_environment: str | None
) -> list[dict[str, Any]]:
    """Return deduped story entrypoints in support-friendly priority order."""

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in sorted(
        [row for row in entrypoints if isinstance(row, dict)],
        key=lambda row: entrypoint_sort_key(
            row,
            selected_environment=selected_environment,
        ),
    ):
        identity = entrypoint_identity(row)
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def selected_environment_for_story(
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
        normalized_value = normalize_environment(value)
        if normalized_value and normalized_value not in normalized_candidates:
            normalized_candidates[normalized_value] = value
    if len(normalized_candidates) == 1:
        return next(iter(normalized_candidates.values()))
    return None


def build_workload_deployment_overview(
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


def entrypoint_labels(entrypoints: list[dict[str, Any]]) -> list[str]:
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


def public_entrypoint_labels(entrypoints: list[dict[str, Any]]) -> list[str]:
    """Return human-friendly labels for public workload entrypoints only."""

    return entrypoint_labels(
        [
            row
            for row in entrypoints
            if isinstance(row, dict)
            and str(row.get("visibility") or "").strip().lower() == "public"
        ]
    )
