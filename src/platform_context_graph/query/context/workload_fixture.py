"""Fixture-backed workload context helpers."""

from __future__ import annotations

from typing import Any

from .database import _portable_repository_ref
from .support import build_fixture_indexes, canonical_ref, edge_evidence


def fixture_workload_context(
    graph: dict[str, Any],
    *,
    workload_id: str,
    environment: str | None = None,
    requested_as: str | None = None,
) -> dict[str, Any]:
    """Build a workload-context response from fixture graph data."""
    entities, edges = build_fixture_indexes(graph)
    workload = entities.get(workload_id)
    if not workload or workload.get("type") != "workload":
        return {"error": f"Workload '{workload_id}' not found"}

    repo_id = workload.get("repo_id")
    repo = entities.get(repo_id) if isinstance(repo_id, str) else None
    instances = [
        entity
        for entity in entities.values()
        if entity.get("type") == "workload_instance"
        and entity.get("workload_id") == workload_id
    ]
    selected_instance = None
    if environment is not None:
        selected_instance = next(
            (
                entity
                for entity in instances
                if entity.get("environment") == environment
            ),
            None,
        )
        if selected_instance is None:
            return {
                "error": (
                    f"Workload '{workload_id}' has no instance for "
                    f"environment '{environment}'"
                )
            }

    source_instances = (
        [selected_instance] if selected_instance is not None else instances
    )
    source_instance_ids = {entity["id"] for entity in source_instances}
    resource_ids = [
        edge["to"]
        for edge in edges
        if edge.get("type") == "USES" and edge.get("from") in source_instance_ids
    ]
    cloud_resources = [
        canonical_ref(entities[resource_id])
        for resource_id in resource_ids
        if resource_id in entities
    ]

    shared_resource_ids = []
    for resource_id in resource_ids:
        consumers = {
            edge.get("from")
            for edge in edges
            if edge.get("type") == "USES" and edge.get("to") == resource_id
        }
        if len(consumers) > 1:
            shared_resource_ids.append(resource_id)
    shared_resources = [
        canonical_ref(entities[resource_id])
        for resource_id in shared_resource_ids
        if resource_id in entities
    ]

    response: dict[str, Any] = {
        "workload": canonical_ref(workload),
        "repositories": [_portable_repository_ref(repo)] if repo else [],
        "cloud_resources": cloud_resources,
        "shared_resources": shared_resources,
        "dependencies": [],
        "entrypoints": [],
        "evidence": edge_evidence(
            edges,
            {
                workload_id,
                *source_instance_ids,
                *resource_ids,
            },
        ),
    }
    if selected_instance is None:
        response["instances"] = [canonical_ref(entity) for entity in instances]
    else:
        response["instance"] = canonical_ref(selected_instance)
    if requested_as:
        response["requested_as"] = requested_as
    return response
