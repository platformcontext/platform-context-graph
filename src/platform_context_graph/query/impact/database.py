"""Database fetch helpers for impact queries."""

from __future__ import annotations

from typing import Any

from .common import edge_from_record, entity_from_record, record_to_dict


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
    else:
        query = "MATCH (n) WHERE n.id = $id RETURN n.id as id, n.name as name LIMIT 1"

    with driver.session() as session:
        record = session.run(query, id=entity_id).single()
    if record is None:
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
    query = (
        "MATCH (source)-[rel]->(target) "
        "WHERE source.id = $id OR target.id = $id "
        "RETURN source.id as source, source.name as source_name, source.type as source_type, "
        "source.kind as source_kind, source.environment as source_environment, "
        "source.workload_id as source_workload_id, source.repo_id as source_repo_id, "
        "target.id as target, target.name as target_name, target.type as target_type, "
        "target.kind as target_kind, target.environment as target_environment, "
        "target.workload_id as target_workload_id, target.repo_id as target_repo_id, "
        "type(rel) as type, rel.confidence as confidence, rel.reason as reason, rel.evidence as evidence"
    )
    with driver.session() as session:
        rows = session.run(query, id=entity_id).data()
    edges: list[dict[str, Any]] = []
    for row in rows:
        record = record_to_dict(row)
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
