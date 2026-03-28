"""Database-backed context queries for workloads and services."""

from __future__ import annotations

from typing import Any

from ..repositories import _repository_projection
from .support import (
    build_fixture_indexes,
    canonical_ref,
    edge_evidence,
    infer_workload_kind,
    parse_workload_id,
    record_to_dict,
)


def _portable_repository_ref(row: dict[str, Any]) -> dict[str, Any]:
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


def db_workload_context(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
    requested_as: str | None = None,
) -> dict[str, Any]:
    """Build a workload-context response from the live database."""
    db_manager = (
        database
        if callable(getattr(database, "get_driver", None))
        else getattr(database, "db_manager", database)
    )
    workload_name, parsed_environment = parse_workload_id(workload_id)
    effective_environment = environment or parsed_environment

    with db_manager.get_driver().session() as session:
        workload_row = session.run(
            """
            MATCH (w:Workload)
            WHERE w.id = $canonical_workload_id OR w.name = $workload_name
            OPTIONAL MATCH (repo:Repository {id: w.repo_id})
            RETURN w.id as id,
                   w.name as name,
                   w.kind as kind,
                   w.repo_id as repo_id,
                   repo.name as repo_name,
                   repo.path as repo_path,
                   coalesce(repo[$local_path_key], repo.path) as repo_local_path,
                   coalesce(repo[$repo_slug_key], '') as repo_slug,
                   coalesce(repo[$remote_url_key], '') as repo_remote_url,
                   coalesce(repo[$has_remote_key], false) as repo_has_remote
            LIMIT 1
            """,
            canonical_workload_id=f"workload:{workload_name}",
            workload_name=workload_name,
            local_path_key="local_path",
            repo_slug_key="repo_slug",
            remote_url_key="remote_url",
            has_remote_key="has_remote",
        ).single()
        instance_rows = session.run(
            """
            MATCH (i:WorkloadInstance)
            WHERE i.workload_id = $canonical_workload_id
              AND ($environment IS NULL OR i.environment = $environment)
            RETURN i.id as id,
                   i.name as name,
                   i.kind as kind,
                   i.environment as environment,
                   i.workload_id as workload_id,
                   i.repo_id as repo_id
            ORDER BY i.environment
            """,
            canonical_workload_id=f"workload:{workload_name}",
            environment=effective_environment,
        ).data()
        dependency_rows = session.run(
            """
            MATCH (w:Workload)-[rel]->(dep:Workload)
            WHERE w.id = $canonical_workload_id
              AND type(rel) = $depends_on_type
            RETURN dep.id as id, dep.name as name, dep.kind as kind, dep.repo_id as repo_id
            ORDER BY dep.name
            """,
            canonical_workload_id=f"workload:{workload_name}",
            depends_on_type="DEPENDS_ON",
        ).data()
        repo = session.run(
            f"""
            MATCH (r:Repository)
            WHERE r.name CONTAINS $name
            RETURN {_repository_projection()}
        """,
            name=workload_name,
            local_path_key="local_path",
            remote_url_key="remote_url",
            repo_slug_key="repo_slug",
            has_remote_key="has_remote",
        ).single()
        resource_rows = session.run(
            """
            MATCH (k:K8sResource)
            WHERE k.name CONTAINS $name
            RETURN k.name as name, k.kind as kind, k.namespace as namespace
        """,
            name=workload_name,
        ).data()

    workload_dict = record_to_dict(workload_row) if workload_row is not None else {}
    if workload_dict:
        repo_ref = None
        if workload_dict.get("repo_id"):
            repo_ref = _portable_repository_ref(
                {
                    "id": workload_dict["repo_id"],
                    "name": workload_dict.get("repo_name") or workload_name,
                    "repo_slug": workload_dict.get("repo_slug") or None,
                    "remote_url": workload_dict.get("repo_remote_url") or None,
                    "has_remote": workload_dict.get("repo_has_remote"),
                }
            )
        workload_ref = canonical_ref(
            {
                "id": workload_dict["id"],
                "type": "workload",
                "kind": workload_dict.get("kind") or "service",
                "name": workload_dict.get("name") or workload_name,
            }
        )
        instances = [
            canonical_ref(
                {
                    **record_to_dict(row),
                    "type": "workload_instance",
                }
            )
            for row in instance_rows
        ]
        selected_instance = (
            instances[0] if effective_environment is not None and instances else None
        )
        if effective_environment is not None and selected_instance is None:
            return {
                "error": (
                    f"Workload '{workload_dict['id']}' has no instance for "
                    f"environment '{effective_environment}'"
                )
            }
        return {
            "workload": workload_ref,
            "instance": selected_instance,
            "instances": [] if selected_instance is not None else instances,
            "repositories": [repo_ref] if repo_ref else [],
            "cloud_resources": [],
            "shared_resources": [],
            "dependencies": [
                canonical_ref(
                    {
                        "id": row["id"],
                        "type": "workload",
                        "kind": row.get("kind") or "service",
                        "name": row.get("name"),
                    }
                )
                for row in dependency_rows
                if row.get("id") and row.get("name")
            ],
            "entrypoints": [],
            "evidence": [],
            **({"requested_as": requested_as} if requested_as else {}),
        }

    if repo is None and not resource_rows:
        return {"error": f"Workload '{workload_id}' not found"}

    repo_dict = record_to_dict(repo) if repo is not None else None
    resource_dicts = [record_to_dict(row) for row in resource_rows]
    resource_kinds = [str(row.get("kind", "")).lower() for row in resource_dicts]
    workload_kind = infer_workload_kind(workload_name, resource_kinds)

    workload_ref = canonical_ref(
        {
            "id": f"workload:{workload_name}",
            "type": "workload",
            "kind": workload_kind,
            "name": workload_name,
        }
    )
    instances = [
        canonical_ref(
            {
                "id": f"workload-instance:{workload_name}:{row.get('namespace') or 'default'}",
                "type": "workload_instance",
                "kind": workload_kind,
                "name": workload_name,
                "environment": row.get("namespace") or "default",
                "workload_id": f"workload:{workload_name}",
            }
        )
        for row in resource_dicts
    ]
    selected_instance = None
    if effective_environment is not None:
        selected_instance = canonical_ref(
            {
                "id": f"workload-instance:{workload_name}:{effective_environment}",
                "type": "workload_instance",
                "kind": workload_kind,
                "name": workload_name,
                "environment": effective_environment,
                "workload_id": f"workload:{workload_name}",
            }
        )

    response: dict[str, Any] = {
        "workload": workload_ref,
        "repositories": ([_portable_repository_ref(repo_dict)] if repo_dict else []),
        "cloud_resources": [],
        "shared_resources": [],
        "dependencies": [],
        "entrypoints": [],
        "evidence": [],
    }
    if selected_instance is not None:
        response["instance"] = selected_instance
    else:
        response["instances"] = instances
    if requested_as:
        response["requested_as"] = requested_as
    return response


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

    resource_ids = [
        edge["to"]
        for edge in edges
        if edge.get("type") == "USES"
        and edge.get("from") in {entity["id"] for entity in source_instances}
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
                *(entity["id"] for entity in source_instances),
                *(resource_ids),
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
