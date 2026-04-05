"""Context-assembly queries for entities, workloads, and service aliases."""

from __future__ import annotations

from typing import Any

from ...observability import trace_query
from ..story_documentation import (
    build_graph_context_evidence,
    collect_documentation_evidence,
)
from ..story import build_workload_story_response
from .content_entity import content_entity_context
from .database import db_workload_context
from .fixture import fixture_entity_context
from .support import load_fixture_graph, parse_workload_id
from .workload_fixture import fixture_workload_context

__all__ = [
    "ServiceAliasError",
    "get_entity_context",
    "get_service_story",
    "get_workload_context",
    "get_workload_story",
    "get_service_context",
]


class ServiceAliasError(ValueError):
    """Raised when a service-only alias is used for a non-service workload."""


def get_entity_context(
    database: Any,
    *,
    entity_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return context for any canonical entity identifier.

    Args:
        database: Live database manager or fixture graph source.
        entity_id: Canonical entity identifier.
        environment: Optional environment scope for workload entities.

    Returns:
        Context payload for the requested entity, or an error mapping.
    """
    with trace_query("entity_context"):
        return _entity_context(database, entity_id=entity_id, environment=environment)


def get_workload_context(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return logical or environment-scoped workload context."""
    with trace_query("workload_context"):
        return _workload_context(
            database,
            workload_id=workload_id,
            environment=environment,
        )


def get_service_context(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return service context via the workload alias surface.

    Args:
        database: Live database manager or fixture graph source.
        workload_id: Canonical workload identifier.
        environment: Optional environment scope for workload instances.

    Returns:
        Service-context payload or an error mapping.

    Raises:
        ServiceAliasError: If the workload exists but is not of kind
            ``service``.
    """
    with trace_query("service_context"):
        result = _workload_context(
            database,
            workload_id=workload_id,
            environment=environment,
            requested_as="service",
        )
        if "error" in result:
            return result
        if result["workload"].get("kind") != "service":
            raise ServiceAliasError(
                f"Workload '{workload_id}' is not a service and cannot be addressed via service alias"
            )
        return result


def get_workload_story(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return a structured story for one workload."""

    with trace_query("workload_story"):
        result = _workload_context(
            database,
            workload_id=workload_id,
            environment=environment,
        )
        if "error" in result:
            return result
        _attach_documentation_evidence(database, result)
        return build_workload_story_response(result)


def get_service_story(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return a structured story for one service alias."""

    with trace_query("service_story"):
        result = get_service_context(
            database,
            workload_id=workload_id,
            environment=environment,
        )
        if "error" in result:
            return result
        _attach_documentation_evidence(database, result)
        return build_workload_story_response(result)


def _attach_documentation_evidence(database: Any, context: dict[str, Any]) -> None:
    """Attach targeted Postgres-backed documentation evidence in place."""

    workload = dict(context.get("workload") or {})
    subject_name = str(workload.get("name") or "")
    documentation_evidence = collect_documentation_evidence(
        database,
        repo_refs=list(context.get("repositories") or [])
        + list(context.get("deploys_from") or [])
        + list(context.get("discovers_config_in") or [])
        + list(context.get("provisioned_by") or []),
        subject_names=[subject_name] if subject_name else [],
    )
    documentation_evidence["graph_context"] = build_graph_context_evidence(
        entrypoints=list(context.get("entrypoints") or []),
        delivery_paths=list(context.get("delivery_paths") or []),
        deploys_from=list(context.get("deploys_from") or []),
        dependencies=list(context.get("dependencies") or []),
        api_surface=dict(context.get("api_surface") or {}),
    )
    context["documentation_evidence"] = documentation_evidence


def _entity_context(
    database: Any,
    *,
    entity_id: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Dispatch entity-context lookups across fixture and database sources."""
    fixture_graph = load_fixture_graph(database)
    if fixture_graph is not None:
        return fixture_entity_context(
            fixture_graph,
            entity_id=entity_id,
            environment=environment,
        )
    if entity_id.startswith("content-entity:"):
        return content_entity_context(database, entity_id=entity_id)
    if entity_id.startswith("repository:"):
        from .. import repositories as repository_queries

        context = repository_queries.get_repository_context(
            database,
            repo_id=entity_id,
        )
        if "error" in context:
            return context
        context["entity"] = {
            "id": context["repository"]["id"],
            "type": "repository",
            "name": context["repository"]["name"],
            "repo_slug": context["repository"].get("repo_slug"),
            "remote_url": context["repository"].get("remote_url"),
            "local_path": context["repository"].get("local_path"),
            "has_remote": context["repository"].get("has_remote"),
        }
        return context
    if entity_id.startswith("workload-instance:"):
        workload_name, environment_name = parse_workload_id(entity_id)
        result = db_workload_context(
            database,
            workload_id=entity_id,
        )
        if "error" in result:
            return result
        workload_kind = None
        if isinstance(result.get("instance"), dict):
            workload_kind = result["instance"].get("kind")
        if workload_kind is None and isinstance(result.get("workload"), dict):
            workload_kind = result["workload"].get("kind")
        result["entity"] = {
            "id": entity_id,
            "type": "workload_instance",
            "kind": workload_kind,
            "name": workload_name,
            "environment": environment_name,
            "workload_id": f"workload:{workload_name}",
        }
        return result
    if entity_id.startswith("workload:"):
        result = db_workload_context(
            database,
            workload_id=entity_id,
            environment=environment,
        )
        if "error" in result:
            return result
        result["entity"] = result["workload"]
        return result
    return {"error": f"Entity '{entity_id}' is not available without fixture data"}


def _workload_context(
    database: Any,
    *,
    workload_id: str,
    environment: str | None = None,
    requested_as: str | None = None,
) -> dict[str, Any]:
    """Dispatch workload-context lookups across fixture and database sources."""
    fixture_graph = load_fixture_graph(database)
    if fixture_graph is not None:
        return fixture_workload_context(
            fixture_graph,
            workload_id=workload_id,
            environment=environment,
            requested_as=requested_as,
        )
    return db_workload_context(
        database,
        workload_id=workload_id,
        environment=environment,
        requested_as=requested_as,
    )
