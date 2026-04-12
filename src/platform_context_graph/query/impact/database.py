"""Database fetch helpers for impact queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from .common import edge_from_record, entity_from_record, record_to_dict


def _file_entity_id(path: str | None) -> str | None:
    """Return a canonical file entity ID for a file path."""

    if not path:
        return None
    return f"file:{quote(path, safe='')}"


def _file_path(entity_id: str) -> str | None:
    """Return the raw file path encoded in a canonical file entity ID."""

    if not entity_id.startswith("file:"):
        return None
    encoded_path = entity_id.split(":", 1)[1]
    if not encoded_path:
        return None
    return unquote(encoded_path)


def _canonical_endpoint_id(record: dict[str, Any], prefix: str) -> str | None:
    """Return the best canonical identifier for an edge endpoint."""

    direct_ref = record.get(prefix)
    if isinstance(direct_ref, str) and direct_ref:
        return direct_ref
    direct_id = record.get(f"{prefix}_id")
    if isinstance(direct_id, str) and direct_id:
        return direct_id
    direct_uid = record.get(f"{prefix}_uid")
    if isinstance(direct_uid, str) and direct_uid:
        return direct_uid
    path = record.get(f"{prefix}_path")
    labels = record.get(f"{prefix}_labels")
    if isinstance(labels, list) and "File" in labels and isinstance(path, str):
        return _file_entity_id(path)
    return None


def _normalized_edge_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw database edge rows into canonical edge snapshots."""

    source_id = _canonical_endpoint_id(record, "source")
    target_id = _canonical_endpoint_id(record, "target")
    if not source_id or not target_id:
        return {}
    return {
        "source": source_id,
        "target": target_id,
        "type": record.get("type"),
        "confidence": record.get("confidence"),
        "reason": record.get("reason"),
        "evidence": record.get("evidence"),
    }


def _edge_query(where_clause: str) -> str:
    """Return the shared Cypher used to fetch connected graph edges."""

    return (
        "MATCH (source)-[rel]->(target) "
        f"WHERE {where_clause} "
        "RETURN source.id as source_id, source.uid as source_uid, "
        "source.path as source_path, labels(source) as source_labels, "
        "target.id as target_id, target.uid as target_uid, "
        "target.path as target_path, labels(target) as target_labels, "
        "type(rel) as type, rel.confidence as confidence, "
        "rel.reason as reason, rel.evidence as evidence"
    )


def db_fetch_entity(database: Any, entity_id: str) -> dict[str, Any] | None:
    """Load a single entity snapshot from the backing database.

    Args:
        database: Query-layer database dependency.
        entity_id: Canonical entity identifier.

    Returns:
        Entity snapshot when found, otherwise ``None``.
    """

    driver = database.get_driver()
    if entity_id.startswith("repository:"):
        query = (
            "MATCH (r:Repository) "
            "WHERE r.id = $id "
            "RETURN r.id as id, r.name as name, r.path as path LIMIT 1"
        )
    elif entity_id.startswith("workload-instance:"):
        query = (
            "MATCH (i:WorkloadInstance) "
            "WHERE i.id = $id "
            "RETURN i.id as id, i.name as name, i.kind as kind, i.environment as environment, "
            "i.workload_id as workload_id, i.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("workload:"):
        query = (
            "MATCH (w:Workload) "
            "WHERE w.id = $id "
            "RETURN w.id as id, w.name as name, w.kind as kind, w.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("terraform-module:"):
        query = (
            "MATCH (m:TerraformModule) "
            "WHERE m.id = $id "
            "RETURN m.id as id, m.name as name, m.source as source, m.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("cloud-resource:"):
        query = (
            "MATCH (c:CloudResource) "
            "WHERE c.id = $id "
            "RETURN c.id as id, c.name as name, c.environment as environment, c.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("content-entity:"):
        query = (
            "MATCH (n) "
            "WHERE n.uid = $id "
            "RETURN coalesce(n.uid, n.id) as id, n.name as name, "
            "'content_entity' as type, n.path as path, n.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("data-asset:"):
        query = (
            "MATCH (n:DataAsset) "
            "WHERE n.id = $id "
            "RETURN n.id as id, n.name as name, "
            "'data_asset' as type, n.path as path, n.repo_id as repo_id, "
            "n.owner_names as owner_names, n.owner_teams as owner_teams, "
            "n.contract_names as contract_names, "
            "n.contract_levels as contract_levels, "
            "n.change_policies as change_policies, "
            "n.sensitivity as sensitivity, "
            "n.is_protected as is_protected, "
            "n.protection_kind as protection_kind LIMIT 1"
        )
    elif entity_id.startswith("data-column:"):
        query = (
            "MATCH (n:DataColumn) "
            "WHERE n.id = $id "
            "RETURN n.id as id, n.name as name, "
            "'data_column' as type, n.path as path, n.repo_id as repo_id, "
            "n.owner_names as owner_names, n.owner_teams as owner_teams, "
            "n.contract_names as contract_names, "
            "n.contract_levels as contract_levels, "
            "n.change_policies as change_policies, "
            "n.sensitivity as sensitivity, "
            "n.is_protected as is_protected, "
            "n.protection_kind as protection_kind LIMIT 1"
        )
    elif entity_id.startswith("analytics-model:"):
        query = (
            "MATCH (n:AnalyticsModel) "
            "WHERE n.id = $id "
            "RETURN n.id as id, n.name as name, "
            "'analytics_model' as type, coalesce(n.compiled_path, n.path) as path, "
            "n.repo_id as repo_id, "
            "n.parse_state as parse_state, "
            "n.confidence as confidence, "
            "n.materialization as materialization, "
            "n.projection_count as projection_count, "
            "n.unresolved_reference_count as unresolved_reference_count, "
            "n.unresolved_reference_reasons as unresolved_reference_reasons, "
            "n.unresolved_reference_expressions as unresolved_reference_expressions "
            "LIMIT 1"
        )
    elif entity_id.startswith("query-execution:"):
        query = (
            "MATCH (n:QueryExecution) "
            "WHERE n.id = $id "
            "RETURN n.id as id, n.name as name, "
            "'query_execution' as type, n.path as path, n.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("dashboard-asset:"):
        query = (
            "MATCH (n:DashboardAsset) "
            "WHERE n.id = $id "
            "RETURN n.id as id, n.name as name, "
            "'dashboard_asset' as type, n.path as path, n.repo_id as repo_id LIMIT 1"
        )
    elif entity_id.startswith("data-quality-check:"):
        query = (
            "MATCH (n:DataQualityCheck) "
            "WHERE n.id = $id "
            "RETURN n.id as id, n.name as name, "
            "'data_quality_check' as type, n.path as path, n.repo_id as repo_id, "
            "n.status as status, n.severity as severity, "
            "n.check_type as check_type LIMIT 1"
        )
    elif entity_id.startswith("file:"):
        path = _file_path(entity_id)
        if path is None:
            return None
        query = (
            "MATCH (f:File) "
            "WHERE f.path = $path "
            "OPTIONAL MATCH (repo:Repository)-[:REPO_CONTAINS]->(f) "
            "RETURN $id as id, coalesce(f.relative_path, f.path) as name, "
            "'file' as type, f.path as path, repo.id as repo_id LIMIT 1"
        )
    else:
        query = "MATCH (n) WHERE n.id = $id RETURN n.id as id, n.name as name LIMIT 1"

    with driver.session() as session:
        if entity_id.startswith("file:"):
            record = session.run(query, id=entity_id, path=path).single()
        else:
            record = session.run(query, id=entity_id).single()
    if record is None:
        if entity_id.startswith("file:") and path is not None:
            return {
                "id": entity_id,
                "type": "file",
                "name": Path(path).name or path,
                "path": path,
            }
        return None
    return entity_from_record(record)


def db_fetch_workload_instances(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    """Load environment-specific workload instances for a workload.

    Args:
        database: Query-layer database dependency.
        workload_id: Canonical workload identifier.
        environment: Optional environment filter.

    Returns:
        Matching workload-instance snapshots.
    """
    driver = database.get_driver()
    query = (
        "MATCH (i:WorkloadInstance) "
        "WHERE i.workload_id = $workload_id "
        "  AND ($environment IS NULL OR i.environment = $environment) "
        "RETURN i.id as id, i.name as name, i.kind as kind, i.environment as environment, "
        "i.workload_id as workload_id, i.repo_id as repo_id "
        "ORDER BY i.environment"
    )
    with driver.session() as session:
        rows = session.run(
            query, workload_id=workload_id, environment=environment
        ).data()
    instances: list[dict[str, Any]] = []
    for row in rows:
        instance = entity_from_record(row)
        if instance:
            instances.append(instance)
    return instances


def db_fetch_edges(database: Any, entity_id: str) -> list[dict[str, Any]]:
    """Load graph edges connected to an entity from the backing database.

    Args:
        database: Query-layer database dependency.
        entity_id: Canonical entity identifier.

    Returns:
        Connected edge snapshots.
    """

    driver = database.get_driver()
    if entity_id.startswith("content-entity:"):
        query = _edge_query(
            "coalesce(source.id, source.uid) = $id OR "
            "coalesce(target.id, target.uid) = $id"
        )
        params = {"id": entity_id}
    elif entity_id.startswith("file:"):
        path = _file_path(entity_id)
        if path is None:
            return []
        query = _edge_query(
            "(source:File AND source.path = $path) OR "
            "(target:File AND target.path = $path)"
        )
        params = {"path": path}
    else:
        query = _edge_query("source.id = $id OR target.id = $id")
        params = {"id": entity_id}
    with driver.session() as session:
        rows = session.run(query, **params).data()
    edges: list[dict[str, Any]] = []
    for row in rows:
        record = _normalized_edge_record(record_to_dict(row))
        if record:
            edges.append(edge_from_record(record))
    return edges


def db_fetch_argocd_source_repo_edges(
    database: Any,
    *,
    repo_id: str,
    repo_name: str,
) -> list[dict[str, Any]]:
    """Infer deployment-source repository edges from Argo application names.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        repo_name: Human-readable repository name.

    Returns:
        Inferred edge snapshots from the repository to Argo deployment source repos.
    """

    driver = database.get_driver()
    query = (
        "MATCH (app)-[:SOURCES_FROM]->(source_repo:Repository) "
        "WHERE (app:ArgoCDApplication OR app:ArgoCDApplicationSet) "
        "  AND app.name = $repo_name "
        "  AND source_repo.id IS NOT NULL "
        "RETURN app.name as app_name, "
        "       CASE "
        "           WHEN app:ArgoCDApplicationSet THEN 'applicationset' "
        "           ELSE 'application' "
        "       END as app_kind, "
        "       coalesce(app[$source_path_key], app[$source_paths_key], '') as source_paths, "
        "       coalesce(app[$source_roots_key], '') as source_roots, "
        "       source_repo.id as target_repo_id, "
        "       source_repo.name as target_repo_name"
    )
    with driver.session() as session:
        rows = session.run(
            query,
            repo_name=repo_name,
            source_path_key="source_path",
            source_paths_key="source_paths",
            source_roots_key="source_roots",
        ).data()

    edges: list[dict[str, Any]] = []
    for row in rows:
        target_repo_id = row.get("target_repo_id")
        if not target_repo_id or target_repo_id == repo_id:
            continue
        app_kind = row.get("app_kind") or "application"
        app_name = row.get("app_name") or repo_name
        target_repo_name = row.get("target_repo_name") or target_repo_id
        detail_parts = [
            f"ArgoCD {app_kind} '{app_name}' sources manifests from '{target_repo_name}'",
        ]
        if row.get("source_paths"):
            detail_parts.append(f"paths={row['source_paths']}")
        if row.get("source_roots"):
            detail_parts.append(f"roots={row['source_roots']}")
        edges.append(
            {
                "from": repo_id,
                "to": target_repo_id,
                "type": "DEPLOYMENT_SOURCE",
                "confidence": 0.9,
                "reason": (
                    f"ArgoCD {app_kind} '{app_name}' for repository '{repo_name}' "
                    "sources deployment manifests from the target repository"
                ),
                "evidence": [
                    {
                        "source": "argocd",
                        "detail": "; ".join(detail_parts),
                        "weight": 0.9,
                    }
                ],
            }
        )
    return edges


def has_direct_edge(
    edges: list[dict[str, Any]],
    source_id: str,
    target_id: str,
) -> bool:
    """Return whether a direct edge exists between two entities.

    Args:
        edges: Edge snapshots in the graph store.
        source_id: Source entity identifier.
        target_id: Target entity identifier.

    Returns:
        ``True`` when a matching edge is present.
    """

    return any(
        edge.get("from") == source_id and edge.get("to") == target_id for edge in edges
    )
