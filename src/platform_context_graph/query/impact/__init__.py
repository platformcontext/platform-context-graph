"""Public impact query entrypoints."""

from __future__ import annotations

from typing import Any

from ...observability import trace_query
from .common import ref_from_id as _ref_from_id
from .common import ref_from_snapshot as _ref_from_snapshot
from .operations import (
    change_surface_store,
    explain_dependency_path_store,
    path_summary as _path_summary,
    trace_resource_to_code_store,
)
from .store import _GraphStore

__all__ = ["trace_resource_to_code", "explain_dependency_path", "find_change_surface"]


def _resolve_ref_id(value: str | dict[str, Any], field_name: str) -> str:
    """Return a canonical entity identifier from a string or ref mapping."""
    if isinstance(value, str):
        return value
    ref_id = value.get("id")
    if not isinstance(ref_id, str) or not ref_id:
        raise ValueError(f"'{field_name}' must include an 'id' field")
    return ref_id


def trace_resource_to_code(
    database: Any,
    *,
    start: str,
    environment: str | None = None,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Trace a resource or infrastructure node back to code repositories.

    Args:
        database: Query-layer database dependency or fixture source.
        start: Canonical entity ID or entity reference.
        environment: Optional environment preference.
        max_depth: Maximum traversal depth.

    Returns:
        Resource-to-code trace response payload.
    """

    with trace_query("trace_resource_to_code"):
        start_id = _resolve_ref_id(start, "start")
        store = _GraphStore.from_source(
            database,
            [start_id],
            environment=environment,
        )
        return trace_resource_to_code_store(
            store,
            start_id=start_id,
            environment=environment,
            max_depth=max_depth,
        )


def explain_dependency_path(
    database: Any,
    *,
    source: str,
    target: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Explain the dependency path between two entities.

    Args:
        database: Query-layer database dependency or fixture source.
        source: Canonical source ID or entity reference.
        target: Canonical target ID or entity reference.
        environment: Optional environment preference.

    Returns:
        Dependency-path response payload.
    """

    with trace_query("explain_dependency_path"):
        source_id = _resolve_ref_id(source, "source")
        target_id = _resolve_ref_id(target, "target")
        store = _GraphStore.from_source(
            database,
            [source_id, target_id],
            environment=environment,
        )
        return explain_dependency_path_store(
            store,
            source_id=source_id,
            target_id=target_id,
            environment=environment,
            max_depth=8,
        )


def find_change_surface(
    database: Any,
    *,
    target: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return the change surface for a target entity.

    Args:
        database: Query-layer database dependency or fixture source.
        target: Canonical target ID or entity reference.
        environment: Optional environment preference.

    Returns:
        Change-surface response payload.
    """

    with trace_query("find_change_surface"):
        target_id = _resolve_ref_id(target, "target")
        store = _GraphStore.from_source(
            database,
            [target_id],
            environment=environment,
        )
        return change_surface_store(
            store,
            target_id=target_id,
            environment=environment,
            max_depth=8,
        )
