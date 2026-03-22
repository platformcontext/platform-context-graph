"""Fixture-backed context queries for entities, workloads, and services."""

from __future__ import annotations

from typing import Any

from .database import fixture_workload_context
from .support import build_fixture_indexes, canonical_ref, load_fixture_graph


def fixture_entity_context(
    database: Any,
    *,
    entity_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return context for a canonical entity identifier from fixture data."""
    fixture_graph = load_fixture_graph(database)
    if fixture_graph is None:
        return {"error": "Fixture graph is unavailable"}

    entities, _ = build_fixture_indexes(fixture_graph)
    entity = entities.get(entity_id)
    if entity is None:
        return {"error": f"Entity '{entity_id}' not found"}
    if entity["type"] == "workload":
        result = fixture_workload_context(
            fixture_graph,
            workload_id=entity_id,
            environment=environment,
        )
        if "error" in result:
            return result
        result["entity"] = canonical_ref(entity)
        return result
    if entity["type"] == "workload_instance":
        result = fixture_workload_context(
            fixture_graph,
            workload_id=entity["workload_id"],
            environment=entity.get("environment"),
        )
        if "error" in result:
            return result
        result["entity"] = canonical_ref(entity)
        return result
    return {"entity": canonical_ref(entity), "related": []}
