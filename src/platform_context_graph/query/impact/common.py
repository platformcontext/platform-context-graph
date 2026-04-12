"""Shared helpers for impact and change-surface queries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ...core.records import record_to_dict
from ...domain import EntityRef, EntityType, EvidenceItem


def load_fixture_graph(database: Any) -> dict[str, Any] | None:
    """Load an impact query fixture graph when the database is fixture-backed.

    Args:
        database: Database dependency or fixture source.

    Returns:
        Parsed fixture graph when the input points to one, otherwise ``None``.
    """

    if isinstance(database, dict):
        return database
    if isinstance(database, Path):
        return json.loads(database.read_text(encoding="utf-8"))
    if isinstance(database, str):
        path = Path(database)
        if path.exists() and path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def entity_type_from_id(entity_id: str) -> EntityType:
    """Infer an entity type from a canonical entity identifier.

    Args:
        entity_id: Canonical entity identifier.

    Returns:
        Inferred entity type, defaulting to ``repository`` when unknown.
    """

    prefix = entity_id.split(":", 1)[0].replace("-", "_")
    try:
        return EntityType(prefix)
    except ValueError:
        return EntityType.repository


def name_from_id(entity_id: str) -> str:
    """Extract a human-readable name from a canonical entity identifier.

    Args:
        entity_id: Canonical entity identifier.

    Returns:
        Trailing entity name component.
    """

    return entity_id.split(":", 1)[1] if ":" in entity_id else entity_id


def _normalize_entity_type(value: Any, entity_id: str) -> EntityType:
    """Return a canonical entity type, falling back to the ID prefix."""

    if isinstance(value, EntityType):
        return value
    if isinstance(value, str):
        try:
            return EntityType(value)
        except ValueError:
            pass
    return entity_type_from_id(entity_id)


def ref_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a portable entity reference payload from a snapshot dictionary.

    Args:
        snapshot: Raw entity snapshot.

    Returns:
        JSON-ready entity reference payload.
    """

    entity_type = _normalize_entity_type(snapshot.get("type"), snapshot["id"])
    name = snapshot.get("name") or name_from_id(snapshot["id"])
    payload: dict[str, Any] = {
        "id": snapshot["id"],
        "type": entity_type.value,
        "name": name,
    }
    if snapshot.get("kind") is not None:
        payload["kind"] = snapshot["kind"]
    if (
        entity_type in {EntityType.environment, EntityType.workload_instance}
        and snapshot.get("environment") is not None
    ):
        payload["environment"] = snapshot["environment"]
    if (
        entity_type == EntityType.workload_instance
        and snapshot.get("workload_id") is not None
    ):
        payload["workload_id"] = snapshot["workload_id"]
    if snapshot.get("path") is not None:
        payload["path"] = snapshot["path"]
    return EntityRef(**payload).model_dump(mode="json", exclude_none=True)


def ref_from_id(entity_id: str, entity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a portable entity reference from an ID and optional entity snapshot.

    Args:
        entity_id: Canonical entity identifier.
        entity: Optional entity snapshot.

    Returns:
        JSON-ready entity reference payload.
    """

    snapshot = dict(entity or {})
    snapshot["id"] = entity_id
    snapshot.setdefault("type", entity_type_from_id(entity_id).value)
    snapshot.setdefault("name", snapshot.get("name") or name_from_id(entity_id))
    if snapshot["type"] == EntityType.workload.value:
        snapshot.setdefault("kind", "service")
    if snapshot["type"] == EntityType.workload_instance.value:
        snapshot.setdefault("kind", snapshot.get("kind") or "service")
        if "environment" not in snapshot and len(entity_id.split(":")) >= 3:
            snapshot["environment"] = entity_id.split(":")[-1]
        snapshot.setdefault(
            "workload_id", f"workload:{name_from_id(entity_id).split(':', 1)[0]}"
        )
        if snapshot.get("workload_id") and not snapshot["workload_id"].startswith(
            "workload:"
        ):
            snapshot["workload_id"] = f"workload:{snapshot['workload_id']}"
    return ref_from_snapshot(snapshot)


def normalize_evidence(value: Any) -> list[dict[str, Any]]:
    """Normalize mixed evidence values into JSON-ready dictionaries.

    Args:
        value: Evidence items from fixtures or database records.

    Returns:
        Normalized evidence payloads.
    """

    evidence: list[dict[str, Any]] = []
    if not value:
        return evidence
    for item in value:
        if isinstance(item, EvidenceItem):
            evidence.append(item.model_dump(mode="json", exclude_none=True))
        elif isinstance(item, dict):
            evidence.append(
                {
                    "source": item.get("source"),
                    "detail": item.get("detail"),
                    "weight": item.get("weight"),
                }
            )
    return evidence


def dedupe_evidence(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate evidence items while preserving order.

    Args:
        items: Evidence payloads to deduplicate.

    Returns:
        Deduplicated evidence payloads.
    """

    evidence: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for item in items:
        key = (item.get("source"), item.get("detail"))
        if key in seen:
            continue
        seen.add(key)
        evidence.append(item)
    return evidence


def entity_matches_id(entity: dict[str, Any], entity_id: str) -> bool:
    """Return whether an entity snapshot matches a canonical identifier.

    Args:
        entity: Entity snapshot.
        entity_id: Canonical entity identifier.

    Returns:
        ``True`` when the snapshot matches the identifier.
    """

    return entity.get("id") == entity_id


def coerce_entity(entity: dict[str, Any] | None, entity_id: str) -> dict[str, Any]:
    """Ensure an entity snapshot contains the minimum expected fields.

    Args:
        entity: Optional entity snapshot.
        entity_id: Canonical entity identifier.

    Returns:
        Coerced entity snapshot.
    """

    if entity is None:
        return {
            "id": entity_id,
            "type": entity_type_from_id(entity_id).value,
            "name": name_from_id(entity_id),
        }
    snapshot = dict(entity)
    snapshot.setdefault("id", entity_id)
    snapshot.setdefault("type", entity_type_from_id(entity_id).value)
    snapshot.setdefault("name", name_from_id(entity_id))
    if snapshot["type"] == EntityType.workload.value:
        snapshot.setdefault("kind", "service")
    return snapshot


def entity_from_record(record: Any) -> dict[str, Any]:
    """Convert a database record into an entity snapshot.

    Args:
        record: Database record or mapping.

    Returns:
        Normalized entity snapshot.
    """

    data = record_to_dict(record)
    if not data:
        return {}
    entity_id = data.get("id")
    if not entity_id:
        return {}
    entity_type = _normalize_entity_type(data.get("type"), entity_id).value
    snapshot = {
        "id": entity_id,
        "type": entity_type,
        "name": data.get("name") or name_from_id(entity_id),
    }
    for key in (
        "kind",
        "environment",
        "workload_id",
        "repo_id",
        "path",
        "parse_state",
        "confidence",
        "materialization",
        "projection_count",
        "unresolved_reference_count",
        "unresolved_reference_reasons",
        "unresolved_reference_expressions",
        "status",
        "severity",
        "check_type",
        "owner_names",
        "owner_teams",
        "contract_names",
        "contract_levels",
        "change_policies",
        "sensitivity",
        "is_protected",
        "protection_kind",
    ):
        if data.get(key) is not None:
            snapshot[key] = data[key]
    if snapshot["type"] == EntityType.workload.value:
        snapshot.setdefault("kind", "service")
    if snapshot["type"] == EntityType.workload_instance.value:
        snapshot.setdefault("kind", data.get("kind") or "service")
        snapshot.setdefault(
            "workload_id", data.get("workload_id") or f"workload:{snapshot['name']}"
        )
        if snapshot.get("environment") is None and len(entity_id.split(":")) >= 3:
            snapshot["environment"] = entity_id.split(":")[-1]
    return snapshot


def edge_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a database record into a graph edge snapshot.

    Args:
        record: Database record or mapping.

    Returns:
        Normalized edge snapshot.
    """

    return {
        "from": record.get("source") or record.get("from"),
        "to": record.get("target") or record.get("to"),
        "type": record.get("type"),
        "confidence": record.get("confidence"),
        "reason": record.get("reason"),
        "evidence": normalize_evidence(record.get("evidence")),
    }


def graph_from_fixture(
    graph: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Normalize a fixture graph into entity and edge maps.

    Args:
        graph: Raw fixture graph payload.

    Returns:
        Entity and edge collections used by the in-memory graph store.
    """

    entities = {entity["id"]: dict(entity) for entity in graph.get("entities", [])}
    edges = [edge_from_record(edge) for edge in graph.get("edges", [])]
    return entities, edges
