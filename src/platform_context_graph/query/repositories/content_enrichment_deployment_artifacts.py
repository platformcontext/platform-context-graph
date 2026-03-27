"""Deployment-artifact enrichment helpers for related config repositories."""

from __future__ import annotations

from glob import glob
from pathlib import Path
from typing import Any, Callable

import yaml


def extract_related_deployment_artifacts(
    *,
    repo_name: str,
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    resolve_related_repo: Callable[[str], dict[str, Any] | None],
    values_path_patterns: Callable[[str], list[str]],
    infer_environment_from_path: Callable[[str], str | None],
    split_csv: Callable[[Any], list[str]],
) -> dict[str, list[dict[str, Any]]]:
    """Extract deployment artifacts from related values-style config files."""

    charts: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    service_ports: list[dict[str, Any]] = []
    gateways: list[dict[str, Any]] = []
    kustomize_resources: list[dict[str, Any]] = []
    kustomize_patches: list[dict[str, Any]] = []

    related_rows = list(deploys_from) + list(discovers_config_in)
    for row in related_rows:
        repo_candidates = split_csv(row.get("source_repos"))
        if not repo_candidates and isinstance(row.get("name"), str):
            repo_candidates = [str(row["name"])]
        for source_repo in repo_candidates:
            resolved_repo = resolve_related_repo(source_repo)
            if resolved_repo is None:
                continue
            local_path = resolved_repo.get("local_path") or resolved_repo.get("path")
            if not isinstance(local_path, str) or not local_path:
                continue
            repo_root = Path(local_path)
            source_repo_name = str(resolved_repo.get("name") or "")
            for source_path in split_csv(row.get("source_paths")):
                direct_path = repo_root / source_path
                if direct_path.is_file():
                    parsed_direct = _load_yaml_file(direct_path)
                    if parsed_direct is not None:
                        relative_direct_path = str(
                            direct_path.resolve().relative_to(repo_root.resolve())
                        )
                        direct_environment = infer_environment_from_path(
                            relative_direct_path
                        )
                        charts.extend(
                            _extract_chart_rows(
                                parsed_direct,
                                source_repo_name=source_repo_name,
                                relative_path=relative_direct_path,
                                environment=direct_environment,
                            )
                        )
                    resources, patches = _extract_kustomize_rows(
                        repo_root=repo_root,
                        overlay_directory=direct_path.parent,
                        source_repo_name=source_repo_name,
                        infer_environment_from_path=infer_environment_from_path,
                    )
                    kustomize_resources.extend(resources)
                    kustomize_patches.extend(patches)
                for candidate_pattern in values_path_patterns(source_path):
                    for file_path in sorted(glob(str(repo_root / candidate_pattern))):
                        relative_path = str(
                            Path(file_path).resolve().relative_to(repo_root.resolve())
                        )
                        parsed = _load_yaml_file(Path(file_path))
                        if parsed is None:
                            continue
                        environment = infer_environment_from_path(relative_path)
                        images.extend(
                            _extract_image_rows(
                                parsed,
                                source_repo_name=source_repo_name,
                                relative_path=relative_path,
                                environment=environment,
                            )
                        )
                        service_ports.extend(
                            _extract_service_port_rows(
                                parsed,
                                source_repo_name=source_repo_name,
                                relative_path=relative_path,
                                environment=environment,
                            )
                        )
                        gateways.extend(
                            _extract_gateway_rows(
                                parsed,
                                source_repo_name=source_repo_name,
                                relative_path=relative_path,
                                environment=environment,
                            )
                        )

    return {
        "charts": _dedupe_rows(charts),
        "images": _dedupe_rows(images),
        "service_ports": _dedupe_rows(service_ports),
        "gateways": _dedupe_rows(gateways),
        "kustomize_resources": _dedupe_rows(kustomize_resources),
        "kustomize_patches": _dedupe_rows(kustomize_patches),
    }


def _load_yaml_file(path: Path) -> dict[str, Any] | None:
    """Load one YAML file into a mapping when possible."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return document if isinstance(document, dict) else None


def _extract_image_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract image repository and tag rows from one values-style document."""

    image = parsed.get("image")
    if not isinstance(image, dict):
        return []
    repository = image.get("repository")
    if not isinstance(repository, str) or not repository.strip():
        return []
    tag = image.get("tag")
    return [
        {
            "repository": repository.strip(),
            "tag": str(tag).strip() if tag is not None else "",
            "source_repo": source_repo_name,
            "relative_path": relative_path,
            "environment": environment,
        }
    ]


def _extract_chart_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract Helm chart source rows from one config-style document."""

    helm = parsed.get("helm")
    if not isinstance(helm, dict):
        return []
    chart = helm.get("chart")
    repo_url = helm.get("repoURL")
    if not isinstance(chart, str) or not chart.strip():
        return []
    return [
        {
            "repo_url": str(repo_url).strip() if repo_url is not None else "",
            "chart": chart.strip(),
            "version": str(helm.get("version") or "").strip(),
            "release_name": str(helm.get("releaseName") or "").strip(),
            "namespace": str(helm.get("namespace") or "").strip(),
            "source_repo": source_repo_name,
            "relative_path": relative_path,
            "environment": environment,
        }
    ]


def _extract_kustomize_rows(
    *,
    repo_root: Path,
    overlay_directory: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract Kustomize resource and patch rows near one overlay directory."""

    kustomization_path = overlay_directory / "kustomization.yaml"
    if not kustomization_path.is_file():
        return [], []
    resource_rows = _extract_kustomize_resource_rows(
        repo_root=repo_root,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
        visited=set(),
    )
    patch_rows = _extract_kustomize_patch_rows(
        repo_root=repo_root,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
    )
    return resource_rows, patch_rows


def _extract_kustomize_resource_rows(
    *,
    repo_root: Path,
    kustomization_path: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    visited: set[Path],
) -> list[dict[str, Any]]:
    """Extract resource rows from one Kustomize file, following nested bases."""

    resolved_kustomization = kustomization_path.resolve()
    if resolved_kustomization in visited:
        return []
    visited.add(resolved_kustomization)
    parsed = _load_yaml_file(kustomization_path)
    if parsed is None:
        return []
    resources = parsed.get("resources")
    if not isinstance(resources, list):
        return []
    relative_kustomization_path = str(
        resolved_kustomization.relative_to(repo_root.resolve())
    )
    environment = infer_environment_from_path(relative_kustomization_path)
    rows: list[dict[str, Any]] = []
    for resource in resources:
        if not isinstance(resource, str) or not resource.strip():
            continue
        resource_path = (kustomization_path.parent / resource).resolve()
        if not _is_within_repo_root(resource_path, repo_root):
            continue
        if resource_path.is_dir():
            nested_kustomization_path = resource_path / "kustomization.yaml"
            if nested_kustomization_path.is_file():
                rows.extend(
                    _extract_kustomize_resource_rows(
                        repo_root=repo_root,
                        kustomization_path=nested_kustomization_path,
                        source_repo_name=source_repo_name,
                        infer_environment_from_path=infer_environment_from_path,
                        visited=visited,
                    )
                )
            continue
        if not resource_path.is_file():
            continue
        parsed_resource = _load_yaml_file(resource_path)
        if parsed_resource is None:
            continue
        metadata = parsed_resource.get("metadata")
        rows.append(
            {
                "resource_path": str(resource_path.relative_to(repo_root.resolve())),
                "kind": str(parsed_resource.get("kind") or "").strip(),
                "name": str((metadata or {}).get("name") or "").strip()
                if isinstance(metadata, dict)
                else "",
                "source_repo": source_repo_name,
                "relative_path": relative_kustomization_path,
                "environment": environment,
            }
        )
    return rows


def _extract_kustomize_patch_rows(
    *,
    repo_root: Path,
    kustomization_path: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Extract patch target rows from one Kustomize file."""

    parsed = _load_yaml_file(kustomization_path)
    if parsed is None:
        return []
    patches = parsed.get("patches")
    if not isinstance(patches, list):
        return []
    relative_kustomization_path = str(
        kustomization_path.resolve().relative_to(repo_root.resolve())
    )
    environment = infer_environment_from_path(relative_kustomization_path)
    rows: list[dict[str, Any]] = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        target = patch.get("target")
        if not isinstance(target, dict):
            continue
        patch_path = patch.get("path")
        if not isinstance(patch_path, str) or not patch_path.strip():
            continue
        resolved_patch_path = (kustomization_path.parent / patch_path).resolve()
        if not _is_within_repo_root(resolved_patch_path, repo_root):
            continue
        rows.append(
            {
                "patch_path": str(resolved_patch_path.relative_to(repo_root.resolve())),
                "target_kind": str(target.get("kind") or "").strip(),
                "target_name": str(target.get("name") or "").strip(),
                "source_repo": source_repo_name,
                "relative_path": relative_kustomization_path,
                "environment": environment,
            }
        )
    return rows


def _is_within_repo_root(path: Path, repo_root: Path) -> bool:
    """Return whether a resolved path stays within the repository root."""

    try:
        path.relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def _extract_service_port_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract service port rows from one values-style document."""

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


def _extract_gateway_rows(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract gateway parent-ref rows from one values-style document."""

    exposure = parsed.get("exposure")
    if not isinstance(exposure, dict):
        return []
    gateway = exposure.get("gateway")
    if not isinstance(gateway, dict):
        return []
    parent_refs = gateway.get("parentRefs")
    if not isinstance(parent_refs, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in parent_refs:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        rows.append(
            {
                "name": name.strip(),
                "source_repo": source_repo_name,
                "relative_path": relative_path,
                "environment": environment,
            }
        )
    return rows


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique mapping rows in input order."""

    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped
