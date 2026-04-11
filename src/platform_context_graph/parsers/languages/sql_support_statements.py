"""Statement-specific SQL parsing helpers."""

from __future__ import annotations

from typing import Any

from .sql_support_shared import (
    append_entity,
    append_relationship,
    collect_table_mentions,
    first_named_child,
    line_number,
    line_number_for_offset,
    named_children,
    node_text,
    normalize_name,
)


def parse_create_table(
    node: Any,
    source: str,
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Parse one ``CREATE TABLE`` statement."""

    table_node = first_named_child(node, "object_reference")
    if table_node is None:
        return
    table_name = normalize_name(node_text(table_node, source))
    append_entity(
        bucket="sql_tables",
        name=table_name,
        node=node,
        results=results,
        seen_entities=seen_entities,
        sql_entity_type="SqlTable",
        index_source=index_source,
        source=source,
        schema=table_name.rsplit(".", 1)[0] if "." in table_name else None,
        qualified_name=table_name,
    )

    column_definitions = first_named_child(node, "column_definitions")
    if column_definitions is None:
        return

    for definition in column_definitions.named_children:
        if definition.type == "column_definition":
            column_name_node = first_named_child(definition, "identifier")
            if column_name_node is None:
                continue
            column_name = node_text(column_name_node, source)
            qualified_column_name = f"{table_name}.{column_name}"
            data_type = None
            if len(definition.named_children) >= 2:
                data_type = node_text(definition.named_children[1], source)
            append_entity(
                bucket="sql_columns",
                name=qualified_column_name,
                node=definition,
                results=results,
                seen_entities=seen_entities,
                sql_entity_type="SqlColumn",
                index_source=index_source,
                source=source,
                table_name=table_name,
                column_name=column_name,
                data_type=data_type,
            )
            append_relationship(
                results,
                seen_relationships,
                relationship_type="HAS_COLUMN",
                source_name=table_name,
                target_name=qualified_column_name,
                line_number=line_number(definition),
            )
            for referenced_name, _operation, offset in collect_table_mentions(
                node_text(definition, source),
                include_reads=False,
            ):
                append_relationship(
                    results,
                    seen_relationships,
                    relationship_type="REFERENCES_TABLE",
                    source_name=table_name,
                    target_name=referenced_name,
                    line_number=line_number_for_offset(
                        source,
                        definition.start_byte + offset,
                    ),
                )
        elif definition.type == "constraints":
            for referenced_name, _operation, offset in collect_table_mentions(
                node_text(definition, source),
                include_reads=False,
            ):
                append_relationship(
                    results,
                    seen_relationships,
                    relationship_type="REFERENCES_TABLE",
                    source_name=table_name,
                    target_name=referenced_name,
                    line_number=line_number_for_offset(
                        source,
                        definition.start_byte + offset,
                    ),
                )


def parse_create_view(
    node: Any,
    source: str,
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Parse one ``CREATE VIEW`` statement."""

    view_node = first_named_child(node, "object_reference")
    if view_node is None:
        return
    view_name = normalize_name(node_text(view_node, source))
    append_entity(
        bucket="sql_views",
        name=view_name,
        node=node,
        results=results,
        seen_entities=seen_entities,
        sql_entity_type="SqlView",
        index_source=index_source,
        source=source,
        schema=view_name.rsplit(".", 1)[0] if "." in view_name else None,
        qualified_name=view_name,
    )

    query_node = first_named_child(node, "create_query")
    if query_node is None:
        return
    for target_name, operation, offset in collect_table_mentions(
        node_text(query_node, source),
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
            line_number=line_number_for_offset(source, query_node.start_byte + offset),
        )


def parse_create_function(
    node: Any,
    source: str,
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Parse one ``CREATE FUNCTION`` statement."""

    function_node = first_named_child(node, "object_reference")
    if function_node is None:
        return
    function_name = normalize_name(node_text(function_node, source))
    function_language = None
    language_node = first_named_child(node, "function_language")
    if language_node is not None:
        function_language = node_text(language_node, source).split()[-1]
    append_entity(
        bucket="sql_functions",
        name=function_name,
        node=node,
        results=results,
        seen_entities=seen_entities,
        sql_entity_type="SqlFunction",
        index_source=index_source,
        source=source,
        schema=function_name.rsplit(".", 1)[0] if "." in function_name else None,
        qualified_name=function_name,
        function_language=function_language,
    )

    body_node = first_named_child(node, "function_body")
    if body_node is None:
        return
    for target_name, _operation, offset in collect_table_mentions(
        node_text(body_node, source),
        include_reads=True,
    ):
        append_relationship(
            results,
            seen_relationships,
            relationship_type="READS_FROM",
            source_name=function_name,
            target_name=target_name,
            line_number=line_number_for_offset(source, body_node.start_byte + offset),
        )


def parse_create_trigger(
    node: Any,
    source: str,
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Parse one ``CREATE TRIGGER`` statement."""

    references = named_children(node, "object_reference")
    if len(references) < 3:
        return
    trigger_name = normalize_name(node_text(references[0], source))
    table_name = normalize_name(node_text(references[1], source))
    function_name = normalize_name(node_text(references[2], source))
    append_entity(
        bucket="sql_triggers",
        name=trigger_name,
        node=node,
        results=results,
        seen_entities=seen_entities,
        sql_entity_type="SqlTrigger",
        index_source=index_source,
        source=source,
        table_name=table_name,
        function_name=function_name,
    )
    append_relationship(
        results,
        seen_relationships,
        relationship_type="TRIGGERS_ON",
        source_name=trigger_name,
        target_name=table_name,
        line_number=line_number(node),
    )
    append_relationship(
        results,
        seen_relationships,
        relationship_type="EXECUTES",
        source_name=trigger_name,
        target_name=function_name,
        line_number=line_number(node),
    )


def parse_create_index(
    node: Any,
    source: str,
    *,
    results: dict[str, Any],
    seen_entities: dict[str, set[str]],
    seen_relationships: set[tuple[str, str, str]],
    index_source: bool,
) -> None:
    """Parse one ``CREATE INDEX`` statement."""

    index_name_node = first_named_child(node, "identifier")
    table_node = first_named_child(node, "object_reference")
    if index_name_node is None or table_node is None:
        return
    index_name = normalize_name(node_text(index_name_node, source))
    table_name = normalize_name(node_text(table_node, source))
    append_entity(
        bucket="sql_indexes",
        name=index_name,
        node=node,
        results=results,
        seen_entities=seen_entities,
        sql_entity_type="SqlIndex",
        index_source=index_source,
        source=source,
        table_name=table_name,
    )
    append_relationship(
        results,
        seen_relationships,
        relationship_type="INDEXES",
        source_name=index_name,
        target_name=table_name,
        line_number=line_number(node),
    )


__all__ = [
    "parse_create_function",
    "parse_create_index",
    "parse_create_table",
    "parse_create_trigger",
    "parse_create_view",
]
