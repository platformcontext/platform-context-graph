"""Support helpers for deployment-artifact extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

_TERRAFORM_CONFIG_PATH_RE = re.compile(
    r'(?P<path>/(?:configd|api)/[A-Za-z0-9._/-]+/\*)',
    re.IGNORECASE,
)


def extract_kustomize_rows(
    *,
    repo_root: Path,
    overlay_directory: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    load_yaml_file: Callable[[Path], dict[str, Any] | None],
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
        load_yaml_file=load_yaml_file,
        visited=set(),
    )
    patch_rows = _extract_kustomize_patch_rows(
        repo_root=repo_root,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
        load_yaml_file=load_yaml_file,
    )
    return resource_rows, patch_rows


def extract_config_path_rows_from_kustomize_resources(
    *,
    repo_root: Path,
    overlay_directory: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    load_yaml_file: Callable[[Path], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Extract config-path rows from Kustomize-managed resources."""

    kustomization_path = overlay_directory / "kustomization.yaml"
    if not kustomization_path.is_file():
        return []
    return _extract_config_path_rows_from_kustomization(
        repo_root=repo_root,
        kustomization_path=kustomization_path,
        source_repo_name=source_repo_name,
        infer_environment_from_path=infer_environment_from_path,
        load_yaml_file=load_yaml_file,
        visited=set(),
    )


def _extract_kustomize_resource_rows(
    *,
    repo_root: Path,
    kustomization_path: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    load_yaml_file: Callable[[Path], dict[str, Any] | None],
    visited: set[Path],
) -> list[dict[str, Any]]:
    """Extract resource rows from one Kustomize file, following nested bases."""

    resolved_kustomization = kustomization_path.resolve()
    if resolved_kustomization in visited:
        return []
    visited.add(resolved_kustomization)
    parsed = load_yaml_file(kustomization_path)
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
        if not is_within_repo_root(resource_path, repo_root):
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
                        load_yaml_file=load_yaml_file,
                        visited=visited,
                    )
                )
            continue
        if not resource_path.is_file():
            continue
        parsed_resource = load_yaml_file(resource_path)
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
    load_yaml_file: Callable[[Path], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Extract patch target rows from one Kustomize file."""

    parsed = load_yaml_file(kustomization_path)
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
        if not is_within_repo_root(resolved_patch_path, repo_root):
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


def _extract_config_path_rows_from_kustomization(
    *,
    repo_root: Path,
    kustomization_path: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
    load_yaml_file: Callable[[Path], dict[str, Any] | None],
    visited: set[Path],
) -> list[dict[str, Any]]:
    """Extract config-path rows from resources reachable from one Kustomize file."""

    resolved_kustomization = kustomization_path.resolve()
    if resolved_kustomization in visited:
        return []
    visited.add(resolved_kustomization)
    parsed = load_yaml_file(kustomization_path)
    if parsed is None:
        return []
    resources = parsed.get("resources")
    if not isinstance(resources, list):
        return []
    rows: list[dict[str, Any]] = []
    for resource in resources:
        if not isinstance(resource, str) or not resource.strip():
            continue
        resource_path = (kustomization_path.parent / resource).resolve()
        if not is_within_repo_root(resource_path, repo_root):
            continue
        if resource_path.is_dir():
            nested_kustomization_path = resource_path / "kustomization.yaml"
            if nested_kustomization_path.is_file():
                rows.extend(
                    _extract_config_path_rows_from_kustomization(
                        repo_root=repo_root,
                        kustomization_path=nested_kustomization_path,
                        source_repo_name=source_repo_name,
                        infer_environment_from_path=infer_environment_from_path,
                        load_yaml_file=load_yaml_file,
                        visited=visited,
                    )
                )
            continue
        if not resource_path.is_file():
            continue
        parsed_resource = load_yaml_file(resource_path)
        if parsed_resource is None:
            continue
        relative_resource_path = str(resource_path.relative_to(repo_root.resolve()))
        environment = infer_environment_from_path(relative_resource_path)
        rows.extend(
            extract_config_path_rows_from_resource(
                parsed_resource,
                source_repo_name=source_repo_name,
                relative_path=relative_resource_path,
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
    repo_root: Path,
    source_repo_name: str,
    infer_environment_from_path: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Extract parameter-path rows from Terraform and Terragrunt text files."""

    rows: list[dict[str, Any]] = []
    for file_path in sorted(repo_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix not in {".tf", ".tfvars", ".hcl"}:
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative_path = str(file_path.relative_to(repo_root.resolve()))
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


def is_within_repo_root(path: Path, repo_root: Path) -> bool:
    """Return whether a resolved path stays within the repository root."""

    try:
        path.relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True
