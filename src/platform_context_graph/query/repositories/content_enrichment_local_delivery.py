"""Local deployment-artifact and delivery-path enrichment helpers."""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath
from typing import Any

from ...parsers.languages.kubernetes_manifest import extract_container_images
from ...resolution.platform_families import format_platform_kind_label
from .content_enrichment_support import (
    infer_environment_from_path,
    ordered_unique_environments,
    ordered_unique_strings,
)
from .indexed_file_discovery import discover_repo_files, read_yaml_file

_CHART_FILENAMES = {"chart.yaml", "chart.yml"}
_YAML_SUFFIXES = (".yaml", ".yml")
_DIRECT_KUBERNETES_ROOTS = {"deploy", "deployments", "k8s", "kubernetes", "manifests"}
_EXCLUDED_KUBERNETES_KINDS = {
    "Application",
    "ApplicationSet",
    "HelmRelease",
    "Kustomization",
}
_ARTIFACT_KEYS = (
    "charts",
    "images",
    "service_ports",
    "gateways",
    "k8s_resources",
    "kustomize_resources",
    "kustomize_patches",
    "config_paths",
)
_KUBERNETES_PLATFORM_KINDS = frozenset({"eks", "kubernetes"})


def extract_local_deployment_artifacts(
    database: Any,
    *,
    repo_id: str,
    repo_name: str,
) -> dict[str, list[dict[str, Any]]]:
    """Extract deployment artifacts that live inside the repository itself."""

    yaml_paths = _discover_yaml_paths(database, repo_id)
    charts: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    service_ports: list[dict[str, Any]] = []
    k8s_resources: list[dict[str, Any]] = []

    chart_value_paths: set[str] = set()
    for relative_path in yaml_paths:
        if PurePosixPath(relative_path).name.lower() not in _CHART_FILENAMES:
            continue
        parsed = read_yaml_file(database, repo_id, relative_path)
        if not isinstance(parsed, dict) or not _matches_local_chart(parsed, repo_name):
            continue
        environment = infer_environment_from_path(relative_path)
        chart_root = posixpath.dirname(relative_path)
        charts.append(
            {
                "repo_url": "",
                "chart": str(parsed.get("name") or "").strip(),
                "version": str(parsed.get("version") or "").strip(),
                "release_name": "",
                "namespace": "",
                "source_repo": repo_name,
                "relative_path": relative_path,
                "environment": environment,
            }
        )
        for value_path in _chart_value_paths(chart_root, yaml_paths):
            if value_path in chart_value_paths:
                continue
            chart_value_paths.add(value_path)
            parsed_values = read_yaml_file(database, repo_id, value_path)
            if not isinstance(parsed_values, dict):
                continue
            images.extend(
                _extract_image_rows(
                    parsed_values,
                    source_repo_name=repo_name,
                    relative_path=value_path,
                    environment=infer_environment_from_path(value_path),
                )
            )
            service_ports.extend(
                _extract_service_port_rows(
                    parsed_values,
                    source_repo_name=repo_name,
                    relative_path=value_path,
                    environment=infer_environment_from_path(value_path),
                )
            )

    for relative_path in yaml_paths:
        parsed = read_yaml_file(database, repo_id, relative_path)
        if not isinstance(parsed, dict) or not _is_direct_kubernetes_resource(
            parsed, relative_path
        ):
            continue
        metadata = parsed.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        environment = (
            infer_environment_from_path(relative_path)
            or infer_environment_from_path(str(metadata.get("namespace") or "").strip())
            or str(metadata.get("namespace") or "").strip()
            or None
        )
        kind = str(parsed.get("kind") or "").strip()
        name = str(metadata.get("name") or "").strip()
        k8s_resources.append(
            {
                "resource_path": relative_path,
                "kind": kind,
                "name": name,
                "source_repo": repo_name,
                "relative_path": relative_path,
                "environment": environment,
            }
        )
        images.extend(
            _extract_kubernetes_image_rows(
                parsed,
                source_repo_name=repo_name,
                relative_path=relative_path,
                environment=environment,
            )
        )

    return {
        "charts": _dedupe_rows(charts),
        "images": _dedupe_rows(images),
        "service_ports": _dedupe_rows(service_ports),
        "gateways": [],
        "k8s_resources": _dedupe_rows(k8s_resources),
        "kustomize_resources": [],
        "kustomize_patches": [],
        "config_paths": [],
    }


def merge_deployment_artifacts(
    *artifact_sets: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Merge deployment-artifact mappings while preserving stable ordering."""

    merged: dict[str, list[dict[str, Any]]] = {key: [] for key in _ARTIFACT_KEYS}
    for artifact_set in artifact_sets:
        for key in _ARTIFACT_KEYS:
            merged[key].extend(list(artifact_set.get(key) or []))
    return {
        key: deduped_rows
        for key, rows in merged.items()
        if (deduped_rows := _dedupe_rows(rows))
    }


def build_local_delivery_paths(
    *,
    deployment_artifacts: dict[str, list[dict[str, Any]]],
    platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build evidence-only delivery paths from repository-local artifacts."""

    kubernetes_platforms = [
        row
        for row in platforms
        if isinstance(row, dict)
        and str(row.get("kind") or "").strip() in _KUBERNETES_PLATFORM_KINDS
    ]
    if not kubernetes_platforms:
        return []

    platform_ids = ordered_unique_strings(
        row.get("id") for row in kubernetes_platforms if row.get("id")
    )
    platform_kinds = ordered_unique_strings(
        row.get("kind") for row in kubernetes_platforms if row.get("kind")
    )
    platform_environments = ordered_unique_strings(
        row.get("environment") for row in kubernetes_platforms if row.get("environment")
    )
    paths: list[dict[str, Any]] = []

    chart_paths = ordered_unique_strings(
        posixpath.dirname(str(row.get("relative_path") or "").strip())
        for row in deployment_artifacts.get("charts", [])
        if str(row.get("relative_path") or "").strip()
    )
    if chart_paths:
        chart_config_rows = [
            row
            for row in deployment_artifacts.get("images", [])
            if _is_values_file(str(row.get("relative_path") or "").strip(), chart_paths)
        ]
        config_sources = ordered_unique_strings(
            str(row.get("relative_path") or "").strip() for row in chart_config_rows
        )
        environments = ordered_unique_strings(
            ordered_unique_environments(
                platform_environments
                + [
                    row.get("environment")
                    for row in deployment_artifacts.get("charts", [])
                    if row.get("environment")
                ]
                + [
                    row.get("environment")
                    for row in chart_config_rows
                    if row.get("environment")
                ]
            )
        )
        paths.append(
            {
                "path_kind": "direct",
                "controller": "",
                "delivery_mode": "plain_helm_release",
                "commands": [],
                "supporting_workflows": [],
                "automation_repositories": [],
                "platform_kinds": platform_kinds,
                "platforms": platform_ids,
                "deployment_sources": chart_paths,
                "config_sources": config_sources,
                "provisioning_repositories": [],
                "environments": environments,
                "summary": _local_delivery_summary(
                    delivery_label="Helm deployment",
                    sources=chart_paths,
                    platform_kinds=platform_kinds,
                ),
            }
        )

    manifest_roots = ordered_unique_strings(
        _manifest_root(str(row.get("resource_path") or "").strip())
        for row in deployment_artifacts.get("k8s_resources", [])
        if str(row.get("resource_path") or "").strip()
    )
    if manifest_roots:
        environments = ordered_unique_strings(
            ordered_unique_environments(
                platform_environments
                + [
                    row.get("environment")
                    for row in deployment_artifacts.get("k8s_resources", [])
                    if row.get("environment")
                ]
            )
        )
        paths.append(
            {
                "path_kind": "direct",
                "controller": "",
                "delivery_mode": "plain_kubernetes_manifests",
                "commands": [],
                "supporting_workflows": [],
                "automation_repositories": [],
                "platform_kinds": platform_kinds,
                "platforms": platform_ids,
                "deployment_sources": manifest_roots,
                "config_sources": [],
                "provisioning_repositories": [],
                "environments": environments,
                "summary": _local_delivery_summary(
                    delivery_label="Kubernetes manifest deployment",
                    sources=manifest_roots,
                    platform_kinds=platform_kinds,
                ),
            }
        )
    return paths


def _discover_yaml_paths(database: Any, repo_id: str) -> list[str]:
    """Return ordered repo-relative YAML paths from indexed file discovery."""

    paths: list[str] = []
    for suffix in _YAML_SUFFIXES:
        paths.extend(discover_repo_files(database, repo_id, suffix=suffix))
    return ordered_unique_strings(paths)


def _matches_local_chart(parsed: dict[str, Any], repo_name: str) -> bool:
    """Return whether a local chart appears to package the repository service."""

    chart_name = str(parsed.get("name") or "").strip()
    annotations = parsed.get("annotations")
    app_repo = ""
    if isinstance(annotations, dict):
        app_repo = str(annotations.get("appRepo") or "").strip()
    return bool(chart_name == repo_name or app_repo == repo_name)


def _chart_value_paths(chart_root: str, yaml_paths: list[str]) -> list[str]:
    """Return values-style YAML files that live under one chart root."""

    prefix = chart_root.rstrip("/") + "/"
    return [
        path
        for path in yaml_paths
        if path.startswith(prefix)
        and PurePosixPath(path).name.lower().startswith("values")
    ]


def _is_direct_kubernetes_resource(parsed: dict[str, Any], relative_path: str) -> bool:
    """Return whether a YAML document looks like a direct Kubernetes manifest."""

    kind = str(parsed.get("kind") or "").strip()
    api_version = str(parsed.get("apiVersion") or "").strip()
    if not kind or not api_version or kind in _EXCLUDED_KUBERNETES_KINDS:
        return False
    return _manifest_root(relative_path) != relative_path


def _extract_image_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract image rows from a Helm values-style document."""

    image = parsed.get("image")
    if not isinstance(image, dict):
        return []
    repository = image.get("repository")
    if not isinstance(repository, str) or not repository.strip():
        return []
    return [
        {
            "repository": repository.strip(),
            "tag": str(image.get("tag") or "").strip(),
            "source_repo": source_repo_name,
            "relative_path": relative_path,
            "environment": environment,
        }
    ]


def _extract_service_port_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract service-port rows from a Helm values-style document."""

    service = parsed.get("service")
    if not isinstance(service, dict):
        return []
    port = service.get("port")
    if port is None:
        return []
    return [
        {
            "port": str(port).strip(),
            "source_repo": source_repo_name,
            "relative_path": relative_path,
            "environment": environment,
        }
    ]


def _extract_kubernetes_image_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract image rows from a Kubernetes workload manifest."""

    rows: list[dict[str, Any]] = []
    for image in extract_container_images(parsed):
        repository, tag = _split_image_reference(image)
        rows.append(
            {
                "repository": repository,
                "tag": tag,
                "source_repo": source_repo_name,
                "relative_path": relative_path,
                "environment": environment,
            }
        )
    return rows


def _split_image_reference(image: str) -> tuple[str, str]:
    """Split a container image reference into repository and tag parts."""

    normalized = image.strip()
    if not normalized:
        return "", ""
    name_part, has_digest, digest_part = normalized.partition("@")
    digest_suffix = f"@{digest_part}" if has_digest else ""
    last_colon = name_part.rfind(":")
    last_slash = name_part.rfind("/")
    if last_colon <= last_slash:
        return normalized, ""
    return name_part[:last_colon] + digest_suffix, name_part[last_colon + 1 :]


def _is_values_file(relative_path: str, chart_paths: list[str]) -> bool:
    """Return whether a path is a values-style config file under a chart root."""

    file_name = PurePosixPath(relative_path).name.lower()
    if not file_name.startswith("values"):
        return False
    return any(
        relative_path.startswith(chart_path.rstrip("/") + "/")
        for chart_path in chart_paths
    )


def _manifest_root(resource_path: str) -> str:
    """Return a stable manifest source root for one resource path."""

    parts = PurePosixPath(resource_path).parts
    if not parts:
        return resource_path
    for index, part in enumerate(parts):
        if part in _DIRECT_KUBERNETES_ROOTS:
            return str(PurePosixPath(*parts[: index + 1]))
    return resource_path


def _local_delivery_summary(
    *,
    delivery_label: str,
    sources: list[str],
    platform_kinds: list[str],
) -> str:
    """Build a concise summary for one evidence-only local delivery path."""

    source_clause = ", ".join(sources)
    if platform_kinds:
        platform_label = " / ".join(
            format_platform_kind_label(kind) for kind in platform_kinds
        )
        return (
            f"Indexed deployment artifacts indicate a direct {delivery_label} "
            f"path through {source_clause} onto {platform_label} platforms."
        )
    return (
        f"Indexed deployment artifacts indicate a direct {delivery_label} "
        f"path through {source_clause}."
    )


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique mapping rows in input order."""

    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(key), repr(value)) for key, value in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped
