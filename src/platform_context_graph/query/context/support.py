"""Shared helpers for entity, workload, and service context queries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...core.records import record_to_dict
from ...domain import EntityRef, EntityType


def load_fixture_graph(database: Any) -> dict[str, Any] | None:
    """Load fixture graph data when a query runs against JSON input."""
    if isinstance(database, dict):
        return database
    if isinstance(database, Path):
        return json.loads(database.read_text())
    if isinstance(database, str):
        path = Path(database)
        if path.exists() and path.suffix == ".json":
            return json.loads(path.read_text())
    return None


def canonical_ref(entity: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw entity mapping into a canonical serialized entity ref."""
    entity_type = EntityType(entity["type"])
    raw_path = entity.get("path")
    local_path = entity.get("local_path")
    if (
        entity_type == EntityType.repository
        and local_path is None
        and raw_path is not None
    ):
        local_path = raw_path
        raw_path = None
    ref = EntityRef(
        id=entity["id"],
        type=entity_type,
        kind=entity.get("kind"),
        name=entity["name"],
        environment=(
            entity.get("environment")
            if entity_type in {EntityType.environment, EntityType.workload_instance}
            else None
        ),
        workload_id=entity.get("workload_id"),
        path=raw_path,
        relative_path=entity.get("relative_path"),
        local_path=local_path,
        repo_slug=entity.get("repo_slug"),
        remote_url=entity.get("remote_url"),
        has_remote=entity.get("has_remote"),
    )
    return ref.model_dump(mode="json", exclude_none=True)


def build_fixture_indexes(
    graph: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Build lookup tables used by fixture-backed context queries."""
    entities = {entity["id"]: entity for entity in graph.get("entities", [])}
    edges = list(graph.get("edges", []))
    return entities, edges


def edge_evidence(
    edges: list[dict[str, Any]], entity_ids: set[str]
) -> list[dict[str, Any]]:
    """Collect deduplicated evidence fragments for related entities."""
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for edge in edges:
        if edge.get("from") not in entity_ids and edge.get("to") not in entity_ids:
            continue
        for item in edge.get("evidence", []):
            key = (item.get("source"), item.get("detail"))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                {
                    "source": item.get("source"),
                    "detail": item.get("detail"),
                    "weight": item.get("weight"),
                }
            )
    return evidence


def parse_workload_id(workload_id: str) -> tuple[str, str | None]:
    """Split workload and workload-instance IDs into name and environment parts."""
    parts = workload_id.split(":")
    if len(parts) == 2 and parts[0] == "workload":
        return parts[1], None
    if len(parts) == 3 and parts[0] == "workload-instance":
        return parts[1], parts[2]
    return workload_id, None


def infer_workload_kind(name: str, resource_kinds: list[str]) -> str:
    """Infer a workload kind from its name and associated runtime resources."""
    normalized = name.lower()
    if "cron" in normalized:
        return "cronjob"
    if "worker" in normalized:
        return "worker"
    if "consumer" in normalized:
        return "consumer"
    if "batch" in normalized:
        return "batch"
    if "service" in resource_kinds or "deployment" in resource_kinds:
        return "service"
    return "service"
