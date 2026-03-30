"""Database-backed context queries for workloads and services."""

from __future__ import annotations

from typing import Any

from ..repositories import _repository_projection
from .support import (
    canonical_ref,
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


def _dedupe_entity_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return entity refs deduped by canonical ID while preserving order."""

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _make_workload_instance_ref(
    *,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    environment: str,
) -> dict[str, Any]:
    """Build a canonical workload-instance ref for a derived environment."""

    return canonical_ref(
        {
            "id": f"workload-instance:{workload_name}:{environment}",
            "type": "workload_instance",
            "kind": workload_kind,
            "name": workload_name,
            "environment": environment,
            "workload_id": workload_id,
        }
    )


def _instances_from_resource_rows(
    *,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    resource_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive workload instances from environment-scoped resource rows."""

    instances = [
        _make_workload_instance_ref(
            workload_id=workload_id,
            workload_name=workload_name,
            workload_kind=workload_kind,
            environment=str(row.get("namespace") or "default"),
        )
        for row in resource_rows
        if str(row.get("namespace") or "default").strip()
    ]
    return _dedupe_entity_refs(instances)


def _instances_from_platform_rows(
    *,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    platform_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive workload instances from repository runtime-platform rows."""

    instances: list[dict[str, Any]] = []
    for row in platform_rows:
        environment = str(
            row.get("workload_environment")
            or row.get("environment")
            or row.get("platform_environment")
            or ""
        ).strip()
        if not environment:
            continue
        instances.append(
            _make_workload_instance_ref(
                workload_id=workload_id,
                workload_name=workload_name,
                workload_kind=workload_kind,
                environment=environment,
            )
        )
    return _dedupe_entity_refs(instances)


def _repository_dependencies_from_context(
    repo_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return repository refs that describe deployment/config dependencies."""

    dependencies: list[dict[str, Any]] = []
    for key in ("deploys_from", "discovers_config_in", "provisioned_by"):
        for row in repo_context.get(key) or []:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            dependencies.append(_portable_repository_ref(row))
    return _dedupe_entity_refs(dependencies)


def _repository_entrypoints_from_context(
    repo_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return portable entrypoint details derived from repository context."""

    entrypoints: list[dict[str, Any]] = []
    for row in repo_context.get("hostnames") or []:
        if not isinstance(row, dict):
            continue
        entrypoint = {
            "hostname": row.get("hostname"),
            "environment": row.get("environment"),
            "source_repo": row.get("source_repo"),
            "relative_path": row.get("relative_path"),
            "visibility": row.get("visibility"),
        }
        if entrypoint.get("hostname"):
            entrypoints.append(entrypoint)
    return entrypoints


def _merge_repository_context_into_workload_response(
    database: Any,
    *,
    repo_id: str,
    workload_id: str,
    workload_name: str,
    workload_kind: str,
    response: dict[str, Any],
    effective_environment: str | None,
) -> dict[str, Any]:
    """Merge repo-backed deployment/runtime details into a workload response."""

    from .. import repositories as repository_queries

    repo_context = repository_queries.get_repository_context(database, repo_id=repo_id)
    if "error" in repo_context:
        return response

    existing_dependencies = list(response.get("dependencies") or [])
    response["dependencies"] = _dedupe_entity_refs(
        existing_dependencies + _repository_dependencies_from_context(repo_context)
    )

    existing_entrypoints = list(response.get("entrypoints") or [])
    response["entrypoints"] = existing_entrypoints + [
        entrypoint
        for entrypoint in _repository_entrypoints_from_context(repo_context)
        if entrypoint not in existing_entrypoints
    ]

    if repo_context.get("coverage") is not None:
        response["coverage"] = repo_context["coverage"]
    if repo_context.get("limitations"):
        response["limitations"] = list(repo_context["limitations"])

    derived_instances = _instances_from_platform_rows(
        workload_id=workload_id,
        workload_name=workload_name,
        workload_kind=workload_kind,
        platform_rows=list(repo_context.get("platforms") or []),
    )
    if effective_environment is not None and response.get("instance") is None:
        response["instance"] = next(
            (
                instance
                for instance in derived_instances
                if instance.get("environment") == effective_environment
            ),
            None,
        )
        if response.get("instance") is not None:
            response["instances"] = []
    if response.get("instance") is None:
        existing_instances = list(response.get("instances") or [])
        response["instances"] = _dedupe_entity_refs(existing_instances + derived_instances)
    return response


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
        workload_kind = workload_dict.get("kind") or "service"
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
                "kind": workload_kind,
                "name": workload_dict.get("name") or workload_name,
            }
        )
        graph_instances = [
            canonical_ref(
                {
                    **record_to_dict(row),
                    "type": "workload_instance",
                }
            )
            for row in instance_rows
        ]
        instances = list(graph_instances)
        selected_instance = None
        if effective_environment is not None:
            selected_instance = next(
                (
                    instance
                    for instance in instances
                    if instance.get("environment") == effective_environment
                ),
                None,
            )

        response = {
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
        if workload_dict.get("repo_id"):
            response = _merge_repository_context_into_workload_response(
                database,
                repo_id=workload_dict["repo_id"],
                workload_id=workload_dict["id"],
                workload_name=workload_dict.get("name") or workload_name,
                workload_kind=workload_kind,
                response=response,
                effective_environment=effective_environment,
            )
        if response.get("instance") is None and not response.get("instances"):
            resource_instances = _instances_from_resource_rows(
                workload_id=workload_dict["id"],
                workload_name=workload_dict.get("name") or workload_name,
                workload_kind=workload_kind,
                resource_rows=[record_to_dict(row) for row in resource_rows],
            )
            if effective_environment is not None:
                response["instance"] = next(
                    (
                        instance
                        for instance in resource_instances
                        if instance.get("environment") == effective_environment
                    ),
                    None,
                )
                if response.get("instance") is not None:
                    response["instances"] = []
            if response.get("instance") is None:
                response["instances"] = resource_instances
        if effective_environment is not None and response.get("instance") is None:
            return {
                "error": (
                    f"Workload '{workload_dict['id']}' has no instance for "
                    f"environment '{effective_environment}'"
                )
            }
        return response

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

