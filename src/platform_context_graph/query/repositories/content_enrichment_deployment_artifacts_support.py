"""Support helpers for deployment-artifact extraction."""

from __future__ import annotations

import posixpath
import re
from typing import Any, Callable

from .indexed_file_discovery import (
    discover_repo_files,
    file_exists,
    read_file_content,
    read_yaml_file,
)

_TERRAFORM_CONFIG_PATH_RE = re.compile(
    r"(?P<path>/(?:configd|api)/[A-Za-z0-9._/-]+/\*)",
    re.IGNORECASE,
)


def extract_kustomize_rows(
    *,
    database: Any,
    repo_id: str,
    overlay_directory: str,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract Kustomize resource and patch rows near one overlay directory."""

    kustomization_path = posixpath.join(overlay_directory, "kustomization.yaml")
    if not file_exists(database, repo_id, kustomization_path):
        return [], []
    resource_rows = _extract_kustomize_resource_rows(
        database=database,
        repo_id=repo_id,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
        visited=set(),
    )
    patch_rows = _extract_kustomize_patch_rows(
        database=database,
        repo_id=repo_id,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
    )
    return resource_rows, patch_rows


def extract_config_path_rows_from_kustomize_resources(
    *,
    database: Any,
    repo_id: str,
    overlay_directory: str,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Extract config-path rows from Kustomize-managed resources."""

    kustomization_path = posixpath.join(overlay_directory, "kustomization.yaml")
    if not file_exists(database, repo_id, kustomization_path):
        return []
    return _extract_config_path_rows_from_kustomization(
        database=database,
        repo_id=repo_id,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
        visited=set(),
    )


def _extract_kustomize_resource_rows(
    *,
    database: Any,
    repo_id: str,
    kustomization_path: str,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    visited: set[str],
) -> list[dict[str, Any]]:
    """Extract resource rows from one Kustomize file, following nested bases."""

    normalized = posixpath.normpath(kustomization_path)
    if normalized in visited:
        return []
    visited.add(normalized)
    parsed = read_yaml_file(database, repo_id, kustomization_path)
    if parsed is None:
        return []
    resources = parsed.get("resources")
    if not isinstance(resources, list):
        return []
    environment = infer_environment_from_path(kustomization_path)
    parent_dir = posixpath.dirname(kustomization_path)
    rows: list[dict[str, Any]] = []
    for resource in resources:
        if not isinstance(resource, str) or not resource.strip():
            continue
        resource_path = posixpath.normpath(posixpath.join(parent_dir, resource))
        if not _is_within_repo(resource_path):
            continue
        # Check if resource is a directory by looking for nested kustomization.yaml
        nested_kustomization = posixpath.join(resource_path, "kustomization.yaml")
        if file_exists(database, repo_id, nested_kustomization):
            rows.extend(
                _extract_kustomize_resource_rows(
                    database=database,
                    repo_id=repo_id,
                    kustomization_path=nested_kustomization,
                    source_repo_name=source_repo_name,
                    infer_environment_from_path=infer_environment_from_path,
                    visited=visited,
                )
            )
            continue
        if not file_exists(database, repo_id, resource_path):
            continue
        parsed_resource = read_yaml_file(database, repo_id, resource_path)
        if parsed_resource is None:
            continue
        metadata = parsed_resource.get("metadata")
        rows.append(
            {
                "resource_path": resource_path,
                "kind": str(parsed_resource.get("kind") or "").strip(),
                "name": (
                    str((metadata or {}).get("name") or "").strip()
                    if isinstance(metadata, dict)
                    else ""
                ),
                "source_repo": source_repo_name,
                "relative_path": kustomization_path,
                "environment": environment,
            }
        )
    return rows


def _extract_kustomize_patch_rows(
    *,
    database: Any,
    repo_id: str,
    kustomization_path: str,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Extract patch target rows from one Kustomize file."""

    parsed = read_yaml_file(database, repo_id, kustomization_path)
    if parsed is None:
        return []
    patches = parsed.get("patches")
    if not isinstance(patches, list):
        return []
    environment = infer_environment_from_path(kustomization_path)
    parent_dir = posixpath.dirname(kustomization_path)
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
        resolved_patch_path = posixpath.normpath(posixpath.join(parent_dir, patch_path))
        if not _is_within_repo(resolved_patch_path):
            continue
        rows.append(
            {
                "patch_path": resolved_patch_path,
                "target_kind": str(target.get("kind") or "").strip(),
                "target_name": str(target.get("name") or "").strip(),
                "source_repo": source_repo_name,
                "relative_path": kustomization_path,
                "environment": environment,
            }
        )
    return rows


def _extract_config_path_rows_from_kustomization(
    *,
    database: Any,
    repo_id: str,
    kustomization_path: str,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    visited: set[str],
) -> list[dict[str, Any]]:
    """Extract config-path rows from resources reachable from one Kustomize file."""

    normalized = posixpath.normpath(kustomization_path)
    if normalized in visited:
        return []
    visited.add(normalized)
    parsed = read_yaml_file(database, repo_id, kustomization_path)
    if parsed is None:
        return []
    resources = parsed.get("resources")
    if not isinstance(resources, list):
        return []
    parent_dir = posixpath.dirname(kustomization_path)
    rows: list[dict[str, Any]] = []
    for resource in resources:
        if not isinstance(resource, str) or not resource.strip():
            continue
        resource_path = posixpath.normpath(posixpath.join(parent_dir, resource))
        if not _is_within_repo(resource_path):
            continue
        # Check if resource is a directory by looking for nested kustomization.yaml
        nested_kustomization = posixpath.join(resource_path, "kustomization.yaml")
        if file_exists(database, repo_id, nested_kustomization):
            rows.extend(
                _extract_config_path_rows_from_kustomization(
                    database=database,
                    repo_id=repo_id,
                    kustomization_path=nested_kustomization,
                    source_repo_name=source_repo_name,
                    infer_environment_from_path=infer_environment_from_path,
                    visited=visited,
                )
            )
            continue
        if not file_exists(database, repo_id, resource_path):
            continue
        parsed_resource = read_yaml_file(database, repo_id, resource_path)
        if parsed_resource is None:
            continue
        environment = infer_environment_from_path(resource_path)
        rows.extend(
            extract_config_path_rows_from_resource(
                parsed_resource,
                source_repo_name=source_repo_name,
                relative_path=resource_path,
                environment=environment,
            )
        )
    return rows


def extract_config_path_rows_from_resource(
    parsed: dict[str, Any],
    *,
    source_repo_name: str,
    relative_path: str,
    environment: str | None,
) -> list[dict[str, Any]]:
    """Extract config/parameter paths from a resource policy document."""

    spec = parsed.get("spec")
    if not isinstance(spec, dict):
        return []
    policy_document = spec.get("policyDocument")
    if not isinstance(policy_document, dict):
        return []
    statements = policy_document.get("Statement")
    if not isinstance(statements, list):
        return []
    rows: list[dict[str, Any]] = []
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        resources = statement.get("Resource")
        if isinstance(resources, str):
            resources = [resources]
        if not isinstance(resources, list):
            continue
        for resource in resources:
            if not isinstance(resource, str):
                continue
            path = ssm_parameter_path(resource)
            if not path:
                continue
            rows.append(
                {
                    "path": path,
                    "source_repo": source_repo_name,
                    "relative_path": relative_path,
                    "environment": environment,
                }
            )
    return rows


def extract_config_path_rows_from_terraform_files(
    *,
    database: Any,
    repo_id: str,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Extract parameter-path rows from Terraform and Terragrunt text files."""

    rows: list[dict[str, Any]] = []
    tf_files: list[str] = []
    for suffix in (".tf", ".tfvars", ".hcl"):
        tf_files.extend(discover_repo_files(database, repo_id, suffix=suffix))
    for relative_path in sorted(set(tf_files)):
        content = read_file_content(database, repo_id, relative_path)
        if content is None:
            continue
        environment = infer_environment_from_path(relative_path)
        for match in _TERRAFORM_CONFIG_PATH_RE.finditer(content):
            rows.append(
                {
                    "path": str(match.group("path") or "").strip(),
                    "source_repo": source_repo_name,
                    "relative_path": relative_path,
                    "environment": environment,
                }
            )
    return rows


def ssm_parameter_path(resource: str) -> str | None:
    """Extract the parameter-store path from one resource ARN."""

    marker = ":parameter"
    if marker not in resource:
        return None
    _, _, suffix = resource.partition(marker)
    normalized = suffix.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized if normalized not in {"/", ""} else None


def _is_within_repo(path: str) -> bool:
    """Return whether a normalized relative path stays within the repository root."""

    return not path.startswith("..") and not posixpath.isabs(path)
