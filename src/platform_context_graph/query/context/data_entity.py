"""Context helpers for vendor-neutral data-intelligence entities."""

from __future__ import annotations

from typing import Any

from ..impact import find_change_surface
from ..impact.database import db_fetch_edges, db_fetch_entity
from ...core.records import record_to_dict
from .content_entity import _lookup_repository_ref
from .data_entity_summary import build_data_entity_summary
from .support import canonical_ref

_DATA_ENTITY_TYPES: dict[str, str] = {
    "DataAsset": "data_asset",
    "DataColumn": "data_column",
    "AnalyticsModel": "analytics_model",
    "QueryExecution": "query_execution",
    "DashboardAsset": "dashboard_asset",
    "DataQualityCheck": "data_quality_check",
    "data_asset": "data_asset",
    "data_column": "data_column",
    "analytics_model": "analytics_model",
    "query_execution": "query_execution",
    "dashboard_asset": "dashboard_asset",
    "data_quality_check": "data_quality_check",
}


def data_entity_context(database: Any, *, entity_id: str) -> dict[str, Any]:
    """Build a generic context payload for one data-intelligence entity."""

    db_manager = (
        database
        if callable(getattr(database, "get_driver", None))
        else getattr(database, "db_manager", database)
    )
    if not callable(getattr(db_manager, "get_driver", None)):
        return {"error": f"Entity '{entity_id}' is not available without fixture data"}

    with db_manager.get_driver().session() as session:
        row = session.run(
            """
            MATCH (entity)
            WHERE entity.id = $entity_id
              AND (
                  entity:DataAsset
                  OR entity:DataColumn
                  OR entity:AnalyticsModel
                  OR entity:QueryExecution
                  OR entity:DashboardAsset
                  OR entity:DataQualityCheck
              )
            OPTIONAL MATCH (file:File)-[:CONTAINS]->(entity)
            OPTIONAL MATCH (repo_from_file:Repository)-[:REPO_CONTAINS]->(file)
            OPTIONAL MATCH (repo_from_id:Repository)
            WHERE repo_from_id.id = entity.repo_id
            WITH entity, file, coalesce(repo_from_file, repo_from_id) as repo
            RETURN entity.id as id,
                   entity.name as name,
                   entity.path as path,
                   coalesce(entity.relative_path, file.relative_path) as relative_path,
                   coalesce(entity.repo_id, repo.id) as repo_id,
                   head([
                       label IN labels(entity)
                       WHERE label IN [
                           'DataAsset',
                           'DataColumn',
                           'AnalyticsModel',
                           'QueryExecution',
                           'DashboardAsset',
                           'DataQualityCheck'
                       ]
                       | label
                   ]) as entity_type
            LIMIT 1
            """,
            entity_id=entity_id,
        ).single()

    payload = record_to_dict(row)
    if not payload:
        return {"error": f"Entity '{entity_id}' is not available without fixture data"}

    entity_type = _DATA_ENTITY_TYPES.get(
        str(payload.get("entity_type") or payload.get("type") or "").strip()
    )
    if entity_type is None:
        return {"error": f"Entity '{entity_id}' is not available without fixture data"}

    repo_id = payload.get("repo_id")
    repositories = (
        [_lookup_repository_ref(database, repo_id)] if isinstance(repo_id, str) else []
    )
    entity_snapshot = db_fetch_entity(db_manager, entity_id) or {
        "id": entity_id,
        "type": entity_type,
        "name": payload.get("name") or entity_id,
        "path": payload.get("path"),
        "repo_id": repo_id,
    }
    entity = {
        "id": entity_id,
        "type": entity_type,
        "name": payload.get("name") or entity_id,
    }
    if payload.get("path"):
        entity["path"] = payload["path"]
    if payload.get("relative_path"):
        entity["relative_path"] = payload["relative_path"]
    edges = db_fetch_edges(db_manager, entity_id)
    change_surface = find_change_surface(db_manager, target=entity_id)
    data_intelligence = build_data_entity_summary(
        entity_snapshot,
        edges=edges,
        change_surface=change_surface,
    )

    response = {
        "entity": canonical_ref(entity),
        "related": list(data_intelligence["sample_impacted_entities"]),
        "repositories": [repo for repo in repositories if repo is not None],
        "relative_path": payload.get("relative_path"),
        "entity_type": payload.get("entity_type"),
        "data_intelligence": data_intelligence,
    }
    if data_intelligence.get("lineage_evidence") is not None:
        response["lineage_evidence"] = data_intelligence["lineage_evidence"]
    return response


__all__ = ["data_entity_context"]
