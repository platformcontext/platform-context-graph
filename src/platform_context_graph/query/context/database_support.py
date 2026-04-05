"""Support helpers for database-backed workload context assembly."""

from __future__ import annotations

from typing import Any

from .support import canonical_ref


def portable_repository_ref(row: dict[str, Any]) -> dict[str, Any]:
    """Return a repository reference without server-local path fields."""

    name = row.get("name") or row.get("repo_slug") or row["id"]
    ref = canonical_ref(
        {
            "id": row["id"],
            "type": "repository",
            "name": name,
            "repo_slug": row.get("repo_slug"),
            "remote_url": row.get("remote_url"),
            "has_remote": row.get("has_remote"),
        }
    )
    ref.pop("path", None)
    ref.pop("local_path", None)
    ref.pop("repo_path", None)
    ref.pop("repo_local_path", None)
    return ref


def dedupe_entity_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return entity refs deduped by canonical ID while preserving order."""

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def dedupe_dict_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return dict rows deduped by stable stringified content."""

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for item in items:
        fingerprint = tuple(
            sorted((str(key), str(value)) for key, value in item.items())
        )
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(item)
    return deduped


def make_workload_instance_ref(
    *,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    environment: str,
) -> dict[str, Any]:
    """Build a canonical workload-instance ref for a derived environment."""

    return canonical_ref(
        {
            "id": f"workload-instance:{workload_name}:{environment}",
            "type": "workload_instance",
            "kind": workload_kind,
            "name": workload_name,
            "environment": environment,
            "workload_id": workload_id,
        }
    )


def instances_from_resource_rows(
    *,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    resource_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive workload instances from environment-scoped resource rows."""

    instances = [
        make_workload_instance_ref(
            workload_id=workload_id,
            workload_name=workload_name,
            workload_kind=workload_kind,
            environment=str(row.get("namespace") or "default"),
        )
        for row in resource_rows
        if str(row.get("namespace") or "default").strip()
    ]
    return dedupe_entity_refs(instances)


def instances_from_platform_rows(
    *,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    platform_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive workload instances from repository runtime-platform rows."""

    instances: list[dict[str, Any]] = []
    for row in platform_rows:
        environment = str(
            row.get("workload_environment")
            or row.get("environment")
            or row.get("platform_environment")
            or ""
        ).strip()
        if not environment:
            continue
        instances.append(
            make_workload_instance_ref(
                workload_id=workload_id,
                workload_name=workload_name,
                workload_kind=workload_kind,
                environment=environment,
            )
        )
    return dedupe_entity_refs(instances)


def repository_dependencies_from_context(
    repo_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return repository refs that describe deployment/config dependencies."""

    dependencies: list[dict[str, Any]] = []
    for key in ("deploys_from", "discovers_config_in", "provisioned_by"):
        for row in repo_context.get(key) or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            dependencies.append(portable_repository_ref(row))
    return dedupe_entity_refs(dependencies)


def repository_entrypoints_from_context(
    repo_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return portable entrypoint details derived from repository context."""

    entrypoints: list[dict[str, Any]] = []
    for row in repo_context.get("hostnames") or []:
        if not isinstance(row, dict):
            continue
        entrypoint = {
            "hostname": row.get("hostname"),
            "environment": row.get("environment"),
            "source_repo": row.get("source_repo"),
            "relative_path": row.get("relative_path"),
            "visibility": row.get("visibility"),
        }
        if entrypoint.get("hostname"):
            entrypoints.append(entrypoint)
    return entrypoints
