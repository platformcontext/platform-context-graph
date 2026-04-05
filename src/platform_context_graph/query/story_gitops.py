"""GitOps-focused shaping helpers for story responses."""

from __future__ import annotations

from typing import Any

from .story_shared import human_list


def _dedupe_strings(values: list[str]) -> list[str]:
    """Return non-empty strings in original order without duplicates."""

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _dedupe_rows(
    rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return rows deduped by the given key fields."""

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(str(row.get(field) or "").strip() for field in key_fields)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _infer_value_layer_kind(relative_path: str) -> str:
    """Infer a human-friendly values-layer kind from one relative path."""

    path_lower = relative_path.lower()
    if "/base/" in path_lower:
        return "base_values"
    if "/overlays/" in path_lower:
        return "overlay_values"
    if path_lower.endswith("chart.yaml"):
        return "chart_definition"
    if path_lower.endswith("kustomization.yaml"):
        return "kustomize_layer"
    if "values" in path_lower:
        return "values_file"
    return "config_path"


def _value_layer_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    """Return a stable ordering for layered GitOps files."""

    relative_path = str(row.get("relative_path") or "")
    path_lower = relative_path.lower()
    if "/base/" in path_lower:
        rank = 0
    elif "/overlays/" in path_lower:
        rank = 1
    elif path_lower.endswith("chart.yaml"):
        rank = 2
    elif path_lower.endswith("kustomization.yaml"):
        rank = 3
    else:
        rank = 4
    return (rank, relative_path)


def build_gitops_overview(
    *,
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
    deployment_artifacts: dict[str, Any],
    environments: list[str],
    observed_config_environments: list[str],
    selected_environment: str | None = None,
) -> dict[str, Any] | None:
    """Build a structured GitOps overview from story-ready context rows."""

    source_repositories = _dedupe_rows(
        [*deploys_from, *discovers_config_in, *provisioned_by],
        key_fields=("id", "name", "repo_slug"),
    )
    delivery_controllers = _dedupe_strings(
        [str(row.get("controller") or "") for row in delivery_paths]
    )
    workflow_families = _dedupe_strings(
        [
            str(row.get("controller_kind") or "")
            for row in controller_driven_paths
            if isinstance(row, dict)
        ]
    )
    chart_rows = [
        row for row in deployment_artifacts.get("charts") or [] if isinstance(row, dict)
    ]
    image_rows = [
        row for row in deployment_artifacts.get("images") or [] if isinstance(row, dict)
    ]
    service_port_rows = [
        row
        for row in deployment_artifacts.get("service_ports") or []
        if isinstance(row, dict)
    ]
    config_paths = [
        {
            "relative_path": str(row.get("path") or "").strip(),
            "source_repo": row.get("source_repo"),
            "layer_kind": _infer_value_layer_kind(str(row.get("path") or "")),
        }
        for row in deployment_artifacts.get("config_paths") or []
        if isinstance(row, dict) and str(row.get("path") or "").strip()
    ]
    value_layers = []
    for precedence, row in enumerate(sorted(config_paths, key=_value_layer_sort_key)):
        value_layers.append({**row, "precedence": precedence})

    rendered_resources = [
        {
            "kind": str(row.get("kind") or "ServicePort"),
            "name": row.get("name") or row.get("port"),
            "component": "runtime",
            "source_family": "kustomize" if row.get("kind") else "service_port",
            "source_repo": row.get("source_repo"),
            "relative_path": row.get("relative_path"),
        }
        for row in [
            *[
                item
                for item in deployment_artifacts.get("kustomize_resources") or []
                if isinstance(item, dict)
            ],
            *service_port_rows,
        ]
    ]
    supporting_resources = [
        {
            "kind": "Gateway",
            "name": row.get("name"),
            "component": "ingress",
            "source_family": "gateway",
            "source_repo": row.get("source_repo"),
            "relative_path": row.get("relative_path"),
        }
        for row in deployment_artifacts.get("gateways") or []
        if isinstance(row, dict) and row.get("name")
    ]

    if not any(
        [
            source_repositories,
            delivery_controllers,
            workflow_families,
            chart_rows,
            value_layers,
            rendered_resources,
            supporting_resources,
        ]
    ):
        return None

    return {
        "owner": {
            "source_repositories": source_repositories,
            "delivery_controllers": delivery_controllers,
            "workflow_families": workflow_families,
        },
        "environment": {
            "selected": selected_environment,
            "declared": _dedupe_strings(environments),
            "observed_config": _dedupe_strings(observed_config_environments),
        },
        "chart": {
            "charts": chart_rows,
            "images": image_rows,
            "service_ports": service_port_rows,
        },
        "value_layers": value_layers,
        "rendered_resources": rendered_resources,
        "supporting_resources": supporting_resources,
        "limitations": [],
    }


def summarize_gitops_overview(gitops_overview: dict[str, Any]) -> str:
    """Return a concise GitOps section summary."""

    owner = gitops_overview.get("owner") or {}
    environment = gitops_overview.get("environment") or {}
    controllers = [
        str(value)
        for value in owner.get("delivery_controllers") or []
        if str(value).strip()
    ]
    repos = [
        str(row.get("name") or row.get("repo_slug") or "")
        for row in owner.get("source_repositories") or []
        if isinstance(row, dict)
    ]
    parts: list[str] = []
    if controllers:
        parts.append(f"GitOps flows through {human_list(controllers)}")
    if repos:
        parts.append(f"using {human_list(repos)}")
    selected_environment = str(environment.get("selected") or "").strip()
    if selected_environment:
        parts.append(f"for {selected_environment}")
    if not parts:
        return "GitOps evidence is available for this story."
    return " ".join(parts).strip() + "."
