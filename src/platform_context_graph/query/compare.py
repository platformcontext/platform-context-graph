"""Environment comparison query helpers."""

from __future__ import annotations

from typing import Any

from ..domain import EntityType
from ..observability import trace_query
from .impact import _GraphStore, _path_summary, _ref_from_id, _ref_from_snapshot

__all__ = ["compare_environments"]


def _compare_environment_snapshot(
    store: _GraphStore, *, workload_id: str, environment: str
) -> dict[str, Any]:
    """Build the environment-specific snapshot for one workload instance.

    Args:
        store: Materialized graph store for the comparison roots.
        workload_id: Canonical workload identifier.
        environment: Environment name to resolve.

    Returns:
        A normalized snapshot describing the environment-specific instance and
        its cloud resources.
    """
    workload = store.entities.get(workload_id)
    if workload is None:
        return {
            "environment": environment,
            "status": "missing",
            "instance": None,
            "cloud_resources": [],
            "shared_resources": [],
        }

    instance_id = f"workload-instance:{workload.get('name', workload_id.split(':', 1)[1])}:{environment}"
    instance = store.entities.get(instance_id)

    if instance is None:
        matching_instance = next(
            (
                entity
                for entity in store.entities.values()
                if entity.get("type") == EntityType.workload_instance.value
                and entity.get("workload_id") == workload_id
                and entity.get("environment") == environment
            ),
            None,
        )
        instance = matching_instance

    if instance is None:
        return {
            "environment": environment,
            "status": "missing",
            "instance": None,
            "cloud_resources": [],
            "shared_resources": [],
        }

    instance_ref = _ref_from_snapshot(instance)
    cloud_resources: list[dict[str, Any]] = []
    for step in store.neighbors(instance_ref["id"], environment=environment):
        if (
            step["type"] == "USES"
            and step["to"]["type"] == EntityType.cloud_resource.value
        ):
            cloud_resources.append(
                {
                    **step["to"],
                    "confidence": step["confidence"],
                    "reason": step["reason"],
                    "evidence": step["evidence"],
                    "via": step["from"]["id"],
                }
            )

    deduped_cloud_resources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for resource in sorted(
        cloud_resources,
        key=lambda item: (-float(item.get("confidence") or 0.0), item["id"]),
    ):
        if resource["id"] in seen_ids:
            continue
        seen_ids.add(resource["id"])
        deduped_cloud_resources.append(resource)

    return {
        "environment": environment,
        "status": "present",
        "instance": instance_ref,
        "cloud_resources": deduped_cloud_resources,
        "shared_resources": [],
    }


def _missing_compare_response(*, reason: str, left: str, right: str) -> dict[str, Any]:
    """Build the canonical missing-workload response for comparison queries."""
    return {
        "workload": None,
        "left": {
            "environment": left,
            "status": "missing",
            "instance": None,
            "cloud_resources": [],
            "shared_resources": [],
        },
        "right": {
            "environment": right,
            "status": "missing",
            "instance": None,
            "cloud_resources": [],
            "shared_resources": [],
        },
        "changed": {"cloud_resources": [], "shared_resources": [], "instances": []},
        "confidence": 0.0,
        "reason": reason,
        "evidence": [],
    }


def compare_environments(
    database: Any,
    *,
    workload_id: str | None = None,
    left: str,
    right: str,
) -> dict[str, Any]:
    """Compare two workload environments from the graph.

    Args:
        database: Database or in-memory graph source.
        workload_id: Canonical workload identifier.
        left: Left-hand environment name.
        right: Right-hand environment name.

    Returns:
        A structured comparison payload for the two environments.
    """
    with trace_query("compare_environments"):
        if not workload_id:
            return _missing_compare_response(
                reason="workload_id is required for compare_environments",
                left=left,
                right=right,
            )

        resolved_workload_id = workload_id
        workload_name = (
            resolved_workload_id.split(":", 1)[1]
            if ":" in resolved_workload_id
            else resolved_workload_id
        )
        root_ids = [resolved_workload_id] if resolved_workload_id else []
        if workload_name:
            root_ids.extend(
                [
                    f"workload-instance:{workload_name}:{left}",
                    f"workload-instance:{workload_name}:{right}",
                ]
            )
        store = _GraphStore.from_source(database, root_ids)

        if (
            resolved_workload_id not in store.entities
            or store.entities[resolved_workload_id].get("type")
            != EntityType.workload.value
        ):
            return _missing_compare_response(
                reason=f"Workload '{workload_id}' not found",
                left=left,
                right=right,
            )

        workload = store.entities.get(resolved_workload_id)
        workload_ref = (
            _ref_from_snapshot(workload)
            if workload
            else _ref_from_id(resolved_workload_id)
        )

        left_snapshot = _compare_environment_snapshot(
            store, workload_id=resolved_workload_id, environment=left
        )
        right_snapshot = _compare_environment_snapshot(
            store, workload_id=resolved_workload_id, environment=right
        )

        left_ids = {item["id"] for item in left_snapshot["cloud_resources"]}
        right_ids = {item["id"] for item in right_snapshot["cloud_resources"]}

        changed_cloud_resources = []
        for resource in right_snapshot["cloud_resources"]:
            if resource["id"] not in left_ids:
                changed_cloud_resources.append(
                    {**resource, "change": "added", "environment": right}
                )
        for resource in left_snapshot["cloud_resources"]:
            if resource["id"] not in right_ids:
                changed_cloud_resources.append(
                    {**resource, "change": "removed", "environment": left}
                )

        changed_cloud_resources.sort(
            key=lambda item: (
                -float(item.get("confidence") or 0.0),
                item["id"],
                item["change"],
            )
        )
        top = changed_cloud_resources[0] if changed_cloud_resources else None
        return {
            "workload": workload_ref,
            "left": left_snapshot,
            "right": right_snapshot,
            "changed": {
                "cloud_resources": changed_cloud_resources,
                "shared_resources": [],
                "instances": [],
            },
            "confidence": top["confidence"] if top else 0.0,
            "reason": (
                top["reason"]
                if top
                else f"No differences found between {left} and {right}"
            ),
            "evidence": top["evidence"] if top else [],
        }
