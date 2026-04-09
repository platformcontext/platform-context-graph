"""Projection-row builders for workload finalization."""

from __future__ import annotations

from typing import Iterable

from ..platforms import canonical_platform_id
from ..platforms import infer_runtime_platform_kind


def _infer_workload_kind(name: str, resource_kinds: Iterable[str]) -> str:
    """Infer a workload kind from its name and matched runtime resources."""

    normalized = name.lower()
    if "cron" in normalized:
        return "cronjob"
    if "worker" in normalized:
        return "worker"
    if "consumer" in normalized:
        return "consumer"
    if "batch" in normalized:
        return "batch"
    normalized_resource_kinds = {str(kind).lower() for kind in resource_kinds if kind}
    if normalized_resource_kinds.intersection({"deployment", "service", "statefulset"}):
        return "service"
    return "service"


def build_projection_rows(
    candidate_rows: list[dict[str, object]],
    *,
    deployment_environments: dict[str, list[str]],
) -> tuple[
    dict[str, int],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, str]],
]:
    """Build batched projection payloads from workload candidates."""

    stats = {"workloads": 0, "instances": 0, "deployment_sources": 0}
    workload_rows: list[dict[str, object]] = []
    instance_rows: list[dict[str, object]] = []
    deployment_source_rows: list[dict[str, object]] = []
    runtime_platform_rows: list[dict[str, object]] = []
    repo_descriptors: list[dict[str, str]] = []
    seen_workloads: set[str] = set()
    seen_instances: set[str] = set()
    seen_deployment_sources: set[tuple[str, str]] = set()
    seen_runtime_platforms: set[tuple[str, str]] = set()

    for row in candidate_rows:
        repo_id = str(row.get("repo_id") or "")
        repo_name = str(row.get("repo_name") or "")
        if not repo_id or not repo_name:
            continue
        workload_id = f"workload:{repo_name}"
        workload_kind = _infer_workload_kind(repo_name, row.get("resource_kinds", []))
        repo_descriptors.append(
            {
                "repo_id": repo_id,
                "repo_name": repo_name,
                "workload_id": workload_id,
            }
        )
        if workload_id not in seen_workloads:
            seen_workloads.add(workload_id)
            workload_rows.append(
                {
                    "repo_id": repo_id,
                    "workload_id": workload_id,
                    "workload_kind": workload_kind,
                    "workload_name": repo_name,
                }
            )
            stats["workloads"] += 1

        deployment_repo_id = str(row.get("deployment_repo_id") or "")
        environments = deployment_environments.get(deployment_repo_id, [])
        if not environments:
            environments = [
                namespace
                for namespace in row.get("namespaces", [])
                if namespace and str(namespace).strip()
            ]

        platform_kind = infer_runtime_platform_kind(row.get("resource_kinds", []))
        for environment in environments:
            instance_id = f"workload-instance:{repo_name}:{environment}"
            if instance_id not in seen_instances:
                seen_instances.add(instance_id)
                instance_rows.append(
                    {
                        "environment": environment,
                        "instance_id": instance_id,
                        "repo_id": repo_id,
                        "workload_id": workload_id,
                        "workload_kind": workload_kind,
                        "workload_name": repo_name,
                    }
                )
                stats["instances"] += 1
            if deployment_repo_id:
                deployment_signature = (instance_id, deployment_repo_id)
                if deployment_signature not in seen_deployment_sources:
                    seen_deployment_sources.add(deployment_signature)
                    deployment_source_rows.append(
                        {
                            "deployment_repo_id": deployment_repo_id,
                            "environment": environment,
                            "instance_id": instance_id,
                            "workload_name": repo_name,
                        }
                    )
                    stats["deployment_sources"] += 1
            if platform_kind is None:
                continue
            platform_id = canonical_platform_id(
                kind=platform_kind,
                provider=None,
                name=environment,
                environment=environment,
                region=None,
                locator=None,
            )
            if platform_id is None:
                continue
            platform_signature = (instance_id, platform_id)
            if platform_signature in seen_runtime_platforms:
                continue
            seen_runtime_platforms.add(platform_signature)
            runtime_platform_rows.append(
                {
                    "environment": environment,
                    "instance_id": instance_id,
                    "platform_id": platform_id,
                    "platform_kind": platform_kind,
                    "platform_locator": None,
                    "platform_name": environment,
                    "platform_provider": None,
                    "platform_region": None,
                    "repo_id": repo_id,
                }
            )

    return (
        stats,
        workload_rows,
        instance_rows,
        deployment_source_rows,
        runtime_platform_rows,
        repo_descriptors,
    )


__all__ = ["build_projection_rows"]
