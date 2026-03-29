"""Deployment-artifact enrichment helpers for related config repositories."""

from __future__ import annotations

import posixpath
from typing import Any, Callable

from .content_enrichment_deployment_artifacts_support import (
    extract_config_path_rows_from_terraform_files,
    extract_config_path_rows_from_kustomize_resources,
    extract_kustomize_rows,
)
from .indexed_file_discovery import (
    discover_repo_files,
    file_exists,
    read_yaml_file,
)


def extract_related_deployment_artifacts(
    *,
    database: Any,
    repo_name: str,
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
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
    config_paths: list[dict[str, Any]] = []

    related_rows = list(deploys_from) + list(discovers_config_in)
    for row in related_rows:
        repo_candidates = split_csv(row.get("source_repos"))
        if not repo_candidates and isinstance(row.get("name"), str):
            repo_candidates = [str(row["name"])]
        for source_repo in repo_candidates:
            resolved_repo = resolve_related_repo(source_repo)
            if resolved_repo is None:
                continue
            repo_id = str(resolved_repo.get("id") or "").strip()
            if not repo_id:
                continue
            source_repo_name = str(resolved_repo.get("name") or "")
            for source_path in split_csv(row.get("source_paths")):
                if file_exists(database, repo_id, source_path):
                    parsed_direct = read_yaml_file(database, repo_id, source_path)
                    if parsed_direct is not None:
                        direct_environment = infer_environment_from_path(
                            source_path
                        )
                        charts.extend(
                            _extract_chart_rows(
                                parsed_direct,
                                source_repo_name=source_repo_name,
                                relative_path=source_path,
                                environment=direct_environment,
                            )
                        )
                    overlay_directory = posixpath.dirname(source_path)
                    resources, patches = extract_kustomize_rows(
                        database=database,
                        repo_id=repo_id,
                        overlay_directory=overlay_directory,
                        source_repo_name=source_repo_name,
                        infer_environment_from_path=infer_environment_from_path,
                    )
                    kustomize_resources.extend(resources)
                    kustomize_patches.extend(patches)
                    config_paths.extend(
                        extract_config_path_rows_from_kustomize_resources(
                            database=database,
                            repo_id=repo_id,
                            overlay_directory=overlay_directory,
                            source_repo_name=source_repo_name,
                            infer_environment_from_path=infer_environment_from_path,
                        )
                    )
                for candidate_pattern in values_path_patterns(source_path):
                    matched_files = _resolve_pattern(
                        database, repo_id, candidate_pattern
                    )
                    for relative_path in matched_files:
                        parsed = read_yaml_file(
                            database, repo_id, relative_path
                        )
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
    for row in provisioned_by:
        if not isinstance(row, dict):
            continue
        repo_candidates = split_csv(row.get("source_repos"))
        if not repo_candidates and isinstance(row.get("name"), str):
            repo_candidates = [str(row["name"])]
        for source_repo in repo_candidates:
            resolved_repo = resolve_related_repo(source_repo)
            if resolved_repo is None:
                continue
            repo_id = str(resolved_repo.get("id") or "").strip()
            if not repo_id:
                continue
            config_paths.extend(
                extract_config_path_rows_from_terraform_files(
                    database=database,
                    repo_id=repo_id,
                    source_repo_name=str(resolved_repo.get("name") or ""),
                    infer_environment_from_path=infer_environment_from_path,
                )
            )

    return {
        "charts": _dedupe_rows(charts),
        "images": _dedupe_rows(images),
        "service_ports": _dedupe_rows(service_ports),
        "gateways": _dedupe_rows(gateways),
        "kustomize_resources": _dedupe_rows(kustomize_resources),
        "kustomize_patches": _dedupe_rows(kustomize_patches),
        "config_paths": _dedupe_rows(config_paths),
    }


def _resolve_pattern(
    database: Any, repo_id: str, pattern: str
) -> list[str]:
    """Resolve a glob-style or exact path pattern to indexed file paths.

    If the pattern contains no wildcard characters it is treated as an exact
    file path and looked up directly.  Otherwise the glob pattern is converted
    to a regex for accurate matching via ``discover_repo_files(pattern=...)``.
    """

    if "*" not in pattern and "?" not in pattern:
        if file_exists(database, repo_id, pattern):
            return [pattern]
        return []
    regex = _glob_to_regex(pattern)
    prefix: str | None = None
    wildcard_pos = min(
        (pattern.find(c) for c in ("*", "?") if c in pattern),
        default=len(pattern),
    )
    if wildcard_pos > 0:
        prefix_candidate = pattern[:wildcard_pos]
        last_slash = prefix_candidate.rfind("/")
        if last_slash >= 0:
            prefix = prefix_candidate[: last_slash + 1]
    return discover_repo_files(database, repo_id, prefix=prefix, pattern=regex)


def _glob_to_regex(glob_pattern: str) -> str:
    """Convert a filesystem glob pattern to a Neo4j-compatible regex.

    Handles ``*`` (single segment), ``**`` (any depth), and ``?`` (single char).
    """
    import re as _re

    parts = []
    i = 0
    while i < len(glob_pattern):
        c = glob_pattern[i]
        if c == "*":
            if i + 1 < len(glob_pattern) and glob_pattern[i + 1] == "*":
                parts.append(".*")
                i += 2
                if i < len(glob_pattern) and glob_pattern[i] == "/":
                    i += 1
            else:
                parts.append("[^/]*")
                i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(_re.escape(c))
            i += 1
    return "^" + "".join(parts) + "$"


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
