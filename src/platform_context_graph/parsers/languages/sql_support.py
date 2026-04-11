"""Support helpers for the SQL parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform_context_graph.utils.source_text import read_source_text

from .sql_support_fallbacks import apply_regex_fallbacks
from .sql_support_migrations import build_migration_entries
from .sql_support_shared import statement_nodes
from .sql_support_statements import (
    parse_create_function,
    parse_create_index,
    parse_create_table,
    parse_create_trigger,
    parse_create_view,
)


def parse_sql_file(
    parser: Any,
    path: Path | str,
    *,
    is_dependency: bool = False,
    index_source: bool = False,
) -> dict[str, Any]:
    """Parse a SQL file into the normalized PCG payload structure."""

    file_path = Path(path)
    source = read_source_text(file_path)
    tree = parser.parser.parse(source.encode("utf-8"))
    root = tree.root_node

    results: dict[str, Any] = {
        "path": str(file_path),
        "sql_tables": [],
        "sql_columns": [],
        "sql_views": [],
        "sql_functions": [],
        "sql_triggers": [],
        "sql_indexes": [],
        "sql_relationships": [],
        "sql_migrations": [],
        "is_dependency": is_dependency,
        "lang": parser.language_name,
    }
    seen_entities: dict[str, set[str]] = {
        "sql_tables": set(),
        "sql_columns": set(),
        "sql_views": set(),
        "sql_functions": set(),
        "sql_triggers": set(),
        "sql_indexes": set(),
    }
    seen_relationships: set[tuple[str, str, str]] = set()

    for statement in statement_nodes(root):
        if statement.type == "create_table":
            parse_create_table(
                statement,
                source,
                results=results,
                seen_entities=seen_entities,
                seen_relationships=seen_relationships,
                index_source=index_source,
            )
        elif statement.type == "create_view":
            parse_create_view(
                statement,
                source,
                results=results,
                seen_entities=seen_entities,
                seen_relationships=seen_relationships,
                index_source=index_source,
            )
        elif statement.type == "create_function":
            parse_create_function(
                statement,
                source,
                results=results,
                seen_entities=seen_entities,
                seen_relationships=seen_relationships,
                index_source=index_source,
            )
        elif statement.type == "create_trigger":
            parse_create_trigger(
                statement,
                source,
                results=results,
                seen_entities=seen_entities,
                seen_relationships=seen_relationships,
                index_source=index_source,
            )
        elif statement.type == "create_index":
            parse_create_index(
                statement,
                source,
                results=results,
                seen_entities=seen_entities,
                seen_relationships=seen_relationships,
                index_source=index_source,
            )

    apply_regex_fallbacks(
        source,
        results=results,
        seen_entities=seen_entities,
        seen_relationships=seen_relationships,
        index_source=index_source,
    )
    results["sql_migrations"] = build_migration_entries(file_path, source, results)
    return results


__all__ = ["parse_sql_file"]
