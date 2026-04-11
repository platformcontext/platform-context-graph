"""Regex fallbacks for partially recoverable SQL statements."""

from __future__ import annotations

import re
from typing import Any

from .sql_support_shared import (
    NAME_PATTERN,
    append_entity,
    append_relationship,
    collect_table_mentions,
    line_number_for_offset,
    normalize_name,
    synthetic_node,
)

CREATE_VIEW_FALLBACK_PATTERN = re.compile(
    rf"\bCREATE\s+VIEW\s+(?P<name>{NAME_PATTERN})\s+AS\s+(?P<body>.*?)(?:;|$)",
    re.IGNORECASE | re.DOTALL,
)


def apply_regex_fallbacks(
    source: str,
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Backfill recoverable entities when tree-sitter loses partial statements."""

    for match in CREATE_VIEW_FALLBACK_PATTERN.finditer(source):
        apply_create_view_fallback(
            source,
            match,
            results=results,
            seen_entities=seen_entities,
            seen_relationships=seen_relationships,
            index_source=index_source,
        )


def apply_create_view_fallback(
    source: str,
    match: re.Match[str],
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Backfill one ``CREATE VIEW`` statement from raw SQL text."""

    view_name = normalize_name(match.group("name"))
    view_node = synthetic_node(source, start=match.start(), end=match.end())
    append_entity(
        bucket="sql_views",
        name=view_name,
        node=view_node,
        results=results,
        seen_entities=seen_entities,
        sql_entity_type="SqlView",
        index_source=index_source,
        source=source,
        schema=view_name.rsplit(".", 1)[0] if "." in view_name else None,
        qualified_name=view_name,
    )

    body_start = match.start("body")
    body_text = match.group("body")
    for target_name, operation, offset in collect_table_mentions(
        body_text,
        include_reads=True,
    ):
        if operation != "select":
            continue
        append_relationship(
            results,
            seen_relationships,
            relationship_type="READS_FROM",
            source_name=view_name,
            target_name=target_name,
            line_number=line_number_for_offset(source, body_start + offset),
        )


__all__ = ["apply_regex_fallbacks"]
