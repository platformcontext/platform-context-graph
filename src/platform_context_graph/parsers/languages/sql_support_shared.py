"""Shared SQL parser constants and helper functions."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

NAME_PATTERN = r'(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][\w$]*))*'
FROM_JOIN_PATTERN = re.compile(
    rf"\b(?:FROM|JOIN)\s+(?P<name>{NAME_PATTERN})",
    re.IGNORECASE,
)
UPDATE_PATTERN = re.compile(rf"\bUPDATE\s+(?P<name>{NAME_PATTERN})", re.IGNORECASE)
INSERT_PATTERN = re.compile(
    rf"\bINSERT\s+INTO\s+(?P<name>{NAME_PATTERN})",
    re.IGNORECASE,
)
DELETE_PATTERN = re.compile(
    rf"\bDELETE\s+FROM\s+(?P<name>{NAME_PATTERN})",
    re.IGNORECASE,
)
REFERENCES_PATTERN = re.compile(
    rf"\bREFERENCES\s+(?P<name>{NAME_PATTERN})",
    re.IGNORECASE,
)
ALTER_TABLE_PATTERN = re.compile(
    rf"\bALTER\s+TABLE\s+(?P<name>{NAME_PATTERN})",
    re.IGNORECASE,
)


def statement_nodes(root: Any) -> list[Any]:
    """Return the top-level SQL statement nodes to interpret."""

    statements: list[Any] = []
    for child in root.named_children:
        if child.type == "statement" and child.named_children:
            statements.append(child.named_children[0])
        else:
            statements.append(child)
    return statements


def node_text(node: Any, source: str) -> str:
    """Return the source text spanned by a tree-sitter node."""

    return source[node.start_byte : node.end_byte]


def line_number(node: Any) -> int:
    """Return the 1-based line number for a node."""

    return int(node.start_point[0]) + 1


def normalize_name(raw_name: str) -> str:
    """Normalize quoted or schema-qualified SQL identifiers."""

    parts = [
        part.strip().strip('"').strip("`").strip("[").strip("]")
        for part in raw_name.strip().split(".")
        if part.strip()
    ]
    return ".".join(parts)


def named_children(node: Any, node_type: str) -> list[Any]:
    """Return the named child nodes matching one type."""

    return [child for child in node.named_children if child.type == node_type]


def first_named_child(node: Any, node_type: str) -> Any | None:
    """Return the first named child node matching one type."""

    children = named_children(node, node_type)
    return children[0] if children else None


def entity(
    *,
    name: str,
    node: Any,
    sql_entity_type: str,
    index_source: bool,
    source: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build one normalized SQL entity payload."""

    item = {
        "name": name,
        "line_number": line_number(node),
        "type": "content_entity",
        "sql_entity_type": sql_entity_type,
        **extra,
    }
    if index_source:
        item["source"] = node_text(node, source)
    return item


def append_entity(
    *,
    bucket: str,
    name: str,
    node: Any,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    sql_entity_type: str,
    index_source: bool,
    source: str,
    **extra: Any,
) -> None:
    """Append one SQL entity when it has not already been recorded."""

    if name in seen_entities[bucket]:
        return
    seen_entities[bucket].add(name)
    results[bucket].append(
        entity(
            name=name,
            node=node,
            sql_entity_type=sql_entity_type,
            index_source=index_source,
            source=source,
            **extra,
        )
    )


def append_relationship(
    results: dict[str, Any],
    seen_relationships: set[tuple[str, str, str]],
    *,
    relationship_type: str,
    source_name: str,
    target_name: str,
    line_number: int,
    **extra: Any,
) -> None:
    """Append a relationship hint when the pair has not already been recorded."""

    signature = (relationship_type, source_name, target_name)
    if signature in seen_relationships:
        return
    seen_relationships.add(signature)
    results["sql_relationships"].append(
        {
            "type": relationship_type,
            "source_name": source_name,
            "target_name": target_name,
            "line_number": line_number,
            **extra,
        }
    )


def collect_table_mentions(
    text: str,
    *,
    include_reads: bool,
) -> list[tuple[str, str, int]]:
    """Collect table-name mentions from SQL text along with operation labels."""

    mentions: list[tuple[str, str, int]] = []
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("update", UPDATE_PATTERN),
        ("insert", INSERT_PATTERN),
        ("delete", DELETE_PATTERN),
        ("reference", REFERENCES_PATTERN),
        ("alter", ALTER_TABLE_PATTERN),
    ]
    if include_reads:
        patterns.insert(0, ("select", FROM_JOIN_PATTERN))
    for operation, pattern in patterns:
        for match in pattern.finditer(text):
            mentions.append(
                (normalize_name(match.group("name")), operation, match.start("name"))
            )
    return mentions


def line_number_for_offset(source: str, offset: int) -> int:
    """Return the 1-based line number for a character offset."""

    return source[:offset].count("\n") + 1


def synthetic_node(source: str, *, start: int, end: int) -> Any:
    """Build a minimal node-like object for regex fallback entities."""

    return SimpleNamespace(
        start_byte=start,
        end_byte=end,
        start_point=(line_number_for_offset(source, start) - 1, 0),
    )


__all__ = [
    "NAME_PATTERN",
    "append_entity",
    "append_relationship",
    "collect_table_mentions",
    "first_named_child",
    "line_number",
    "line_number_for_offset",
    "named_children",
    "node_text",
    "normalize_name",
    "statement_nodes",
    "synthetic_node",
]
