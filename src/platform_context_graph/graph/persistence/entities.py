"""Helpers for building graph-node merge queries during indexing."""

from __future__ import annotations

from typing import Any

from ...tools.graph_builder_persistence_unwind import (
    validate_cypher_label,
    validate_cypher_property_keys,
)


def build_entity_merge_statement(
    *,
    label: str,
    item: dict[str, Any],
    file_path: str,
    use_uid_identity: bool,
) -> tuple[str, dict[str, Any]]:
    """Build a graph merge statement for one parsed entity.

    Args:
        label: Graph label for the entity.
        item: Parsed entity payload.
        file_path: Absolute path to the file containing the entity.
        use_uid_identity: Whether to merge the node by its canonical ``uid``.

    Returns:
        Tuple of ``(query, params)`` ready for ``session.run``.
    """
    validate_cypher_label(label)

    params: dict[str, Any] = {
        "file_path": file_path,
        "name": item["name"],
        "line_number": item["line_number"],
    }
    extra_keys = [key for key in item if key not in {"name", "line_number", "path"}]
    validate_cypher_property_keys(extra_keys)
    params.update({key: item[key] for key in extra_keys})

    if use_uid_identity and item.get("uid"):
        identity_clause = "uid: $uid"
    else:
        identity_clause = "name: $name, path: $file_path, line_number: $line_number"

    set_parts = [
        "n.name = $name",
        "n.path = $file_path",
        "n.line_number = $line_number",
    ]
    for key in extra_keys:
        set_parts.append(f"n.{key} = ${key}")

    query = f"""
        MATCH (f:File {{path: $file_path}})
        MERGE (n:{label} {{{identity_clause}}})
        SET {", ".join(set_parts)}
        MERGE (f)-[:CONTAINS]->(n)
    """
    return query, params


__all__ = ["build_entity_merge_statement"]
