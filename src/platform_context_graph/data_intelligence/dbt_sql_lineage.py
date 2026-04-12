"""Compiled SQL lineage helpers for dbt-style manifest normalization."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .dbt_sql_expressions import (
    derived_expression_gap,
    expression_ignored_identifiers,
    expression_partial_reason,
)
from .dbt_sql_identifiers import unqualified_identifiers

_SELECT_CLAUSE_RE = re.compile(
    r"\bselect\b(?P<select>.*?)\bfrom\b", re.IGNORECASE | re.DOTALL
)
_AS_ALIAS_RE = re.compile(
    r"^(?P<expression>.+?)\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)$",
    re.IGNORECASE | re.DOTALL,
)
_QUALIFIED_REFERENCE_RE = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\."
    r"(?P<column>\*|[A-Za-z_][A-Za-z0-9_]*)(?=[^A-Za-z0-9_]|$)"
)
_FROM_RELATION_RE = re.compile(
    r"\b(?:from|join|left\s+join|right\s+join|inner\s+join|full\s+join|cross\s+join)"
    r"\s+(?P<relation>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2})"
    r"(?:\s+(?:as\s+)?(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ColumnLineage:
    """Normalized lineage for one output column."""

    output_column: str
    source_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompiledModelLineage:
    """Normalized lineage extracted from one compiled SQL model."""

    column_lineage: tuple[ColumnLineage, ...]
    unresolved_references: tuple[dict[str, str], ...]
    projection_count: int


@dataclass(frozen=True, slots=True)
class _RelationBinding:
    """Resolved relation metadata for one source alias in a SQL statement."""

    asset_name: str | None
    column_names: tuple[str, ...]
    column_lineage: Mapping[str, tuple[str, ...]]


def extract_compiled_model_lineage(
    compiled_sql: str,
    *,
    model_name: str,
    relation_column_names: Mapping[str, Sequence[str]],
) -> CompiledModelLineage:
    """Extract final model lineage, including simple CTE propagation."""

    cte_queries, final_sql = _split_cte_queries(compiled_sql)
    cte_bindings: dict[str, _RelationBinding] = {}
    unresolved_references: list[dict[str, str]] = []

    for cte_name, cte_sql in cte_queries:
        cte_lineage = _extract_select_lineage(
            cte_sql,
            model_name=model_name,
            relation_bindings=_relation_bindings(
                cte_sql,
                relation_column_names=relation_column_names,
                cte_bindings=cte_bindings,
            ),
        )
        unresolved_references.extend(cte_lineage.unresolved_references)
        cte_bindings[cte_name] = _binding_for_column_lineage(cte_lineage.column_lineage)

    final_lineage = _extract_select_lineage(
        final_sql,
        model_name=model_name,
        relation_bindings=_relation_bindings(
            final_sql,
            relation_column_names=relation_column_names,
            cte_bindings=cte_bindings,
        ),
    )
    unresolved_references.extend(final_lineage.unresolved_references)
    return CompiledModelLineage(
        column_lineage=final_lineage.column_lineage,
        unresolved_references=tuple(unresolved_references),
        projection_count=final_lineage.projection_count,
    )


def _binding_for_column_lineage(
    column_lineage: Sequence[ColumnLineage],
) -> _RelationBinding:
    """Build a CTE relation binding from projected column lineage."""

    lineage_by_name: dict[str, tuple[str, ...]] = {}
    column_names: list[str] = []
    for item in column_lineage:
        lineage_by_name[item.output_column] = item.source_columns
        column_names.append(item.output_column)
    return _RelationBinding(
        asset_name=None,
        column_names=tuple(column_names),
        column_lineage=lineage_by_name,
    )


def _relation_bindings(
    sql: str,
    *,
    relation_column_names: Mapping[str, Sequence[str]],
    cte_bindings: Mapping[str, _RelationBinding],
) -> dict[str, _RelationBinding]:
    """Return relation bindings for asset and CTE aliases in one SQL statement."""

    bindings: dict[str, _RelationBinding] = {}
    for match in _FROM_RELATION_RE.finditer(sql):
        relation_name = match.group("relation").strip()
        alias = (match.group("alias") or "").strip()
        relation_binding = cte_bindings.get(relation_name)
        if relation_binding is None:
            relation_binding = _RelationBinding(
                asset_name=relation_name,
                column_names=tuple(relation_column_names.get(relation_name, ())),
                column_lineage={},
            )

        names = {relation_name}
        if alias and alias.lower() not in {"on", "where", "group", "order", "limit"}:
            names.add(alias)
        else:
            names.add(relation_name.rsplit(".", maxsplit=1)[-1])

        for binding_name in names:
            bindings[binding_name] = relation_binding
    return bindings


def _extract_select_lineage(
    sql: str,
    *,
    model_name: str,
    relation_bindings: Mapping[str, _RelationBinding],
) -> CompiledModelLineage:
    """Extract lineage from one concrete SELECT statement."""

    column_lineage: list[ColumnLineage] = []
    unresolved_references: list[dict[str, str]] = []
    select_items = _extract_select_items(sql)

    for select_item in select_items:
        projection = _lineage_for_projection(
            select_item=select_item,
            relation_bindings=relation_bindings,
            model_name=model_name,
        )
        column_lineage.extend(projection.column_lineage)
        unresolved_references.extend(projection.unresolved_references)

    return CompiledModelLineage(
        column_lineage=tuple(column_lineage),
        unresolved_references=tuple(unresolved_references),
        projection_count=len(select_items),
    )


def _split_cte_queries(compiled_sql: str) -> tuple[list[tuple[str, str]], str]:
    """Split a SQL string into ordered CTE queries and the final SELECT."""

    trimmed = compiled_sql.lstrip()
    if not trimmed[:4].lower() == "with":
        return [], compiled_sql

    queries: list[tuple[str, str]] = []
    index = 4
    length = len(trimmed)

    while index < length:
        while index < length and trimmed[index].isspace():
            index += 1
        name_start = index
        while index < length and (
            trimmed[index].isalnum() or trimmed[index] == "_"
        ):
            index += 1
        cte_name = trimmed[name_start:index].strip()
        if not cte_name:
            break

        while index < length and trimmed[index].isspace():
            index += 1
        if index < length and trimmed[index] == "(":
            index = _consume_balanced_segment(trimmed, index)
            while index < length and trimmed[index].isspace():
                index += 1

        if trimmed[index : index + 2].lower() != "as":
            break
        index += 2
        while index < length and trimmed[index].isspace():
            index += 1
        if index >= length or trimmed[index] != "(":
            break

        query_start = index + 1
        query_end = _consume_balanced_segment(trimmed, index) - 1
        queries.append((cte_name, trimmed[query_start:query_end]))
        index = query_end + 1
        while index < length and trimmed[index].isspace():
            index += 1
        if index < length and trimmed[index] == ",":
            index += 1
            continue
        return queries, trimmed[index:]

    return [], compiled_sql


def _consume_balanced_segment(text: str, start_index: int) -> int:
    """Return the index immediately after one balanced parenthesized segment."""

    depth = 0
    index = start_index
    while index < len(text):
        character = text[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def _extract_select_items(compiled_sql: str) -> list[str]:
    """Extract top-level SELECT projections from SQL text."""

    match = _SELECT_CLAUSE_RE.search(compiled_sql)
    if match is None:
        return []

    select_clause = match.group("select")
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_single_quote = False

    for character in select_clause:
        if character == "'" and (not current or current[-1] != "\\"):
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if character == "(":
                depth += 1
            elif character == ")" and depth > 0:
                depth -= 1
            elif character == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
                continue
        current.append(character)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _lineage_for_projection(
    *,
    select_item: str,
    relation_bindings: Mapping[str, _RelationBinding],
    model_name: str,
) -> CompiledModelLineage:
    """Extract supported source-column lineage from one SELECT item."""

    match = _AS_ALIAS_RE.match(select_item.strip())
    if match:
        expression = match.group("expression").strip()
        output_column = match.group("alias").strip()
    else:
        expression = select_item.strip()
        output_column = _implicit_output_column(expression)

    column_lineage: list[ColumnLineage] = []
    source_columns: list[str] = []
    unresolved_references: list[dict[str, str]] = []
    seen_columns: set[str] = set()
    matched_unqualified_identifiers: set[str] = set()
    matched_unqualified_identifiers.update(expression_ignored_identifiers(expression))

    for reference in _QUALIFIED_REFERENCE_RE.finditer(expression):
        alias = reference.group("alias")
        column = reference.group("column")
        binding = relation_bindings.get(alias)
        matched_unqualified_identifiers.add(alias)
        matched_unqualified_identifiers.add(column)

        resolved_columns = _resolve_reference_columns(
            binding,
            alias=alias,
            column=column,
            model_name=model_name,
        )
        if isinstance(resolved_columns, dict):
            unresolved_references.append(resolved_columns)
            continue
        if column == "*":
            for expanded_output_column, expanded_source_columns in resolved_columns:
                column_lineage.append(
                    ColumnLineage(
                        output_column=expanded_output_column,
                        source_columns=expanded_source_columns,
                    )
                )
            continue
        for source_column in resolved_columns:
            if source_column in seen_columns:
                continue
            seen_columns.add(source_column)
            source_columns.append(source_column)

    for identifier in unqualified_identifiers(
        expression,
        matched_identifiers=matched_unqualified_identifiers,
    ):
        resolved_columns = _resolve_unqualified_reference_columns(
            identifier,
            relation_bindings=relation_bindings,
            model_name=model_name,
        )
        if isinstance(resolved_columns, dict):
            unresolved_references.append(resolved_columns)
            continue
        for source_column in resolved_columns:
            if source_column in seen_columns:
                continue
            seen_columns.add(source_column)
            source_columns.append(source_column)

    if output_column is None and source_columns:
        output_column = source_columns[0].rsplit(".", maxsplit=1)[-1]
    partial_reason = expression_partial_reason(expression)
    if source_columns and partial_reason is not None:
        unresolved_references.append(
            derived_expression_gap(
                expression=expression,
                model_name=model_name,
                reason=partial_reason,
            )
        )
    if output_column is not None and source_columns:
        column_lineage.append(
            ColumnLineage(
                output_column=output_column.strip(),
                source_columns=tuple(source_columns),
            )
        )

    return CompiledModelLineage(
        column_lineage=tuple(column_lineage),
        unresolved_references=tuple(unresolved_references),
        projection_count=1,
    )


def _resolve_reference_columns(
    binding: _RelationBinding | None,
    *,
    alias: str,
    column: str,
    model_name: str,
) -> Sequence[str] | Sequence[tuple[str, tuple[str, ...]]] | dict[str, str]:
    """Resolve one qualified column reference through an asset or CTE binding."""

    if binding is None:
        return {
            "expression": f"{alias}.{column}",
            "model_name": model_name,
            "reason": "source_alias_not_resolved",
        }
    if column == "*":
        if binding.asset_name is not None:
            if not binding.column_names:
                return {
                    "expression": f"{alias}.*",
                    "model_name": model_name,
                    "reason": "wildcard_projection_not_supported",
                }
            return [
                (
                    expanded_column,
                    (f"{binding.asset_name}.{expanded_column}",),
                )
                for expanded_column in binding.column_names
            ]
        if not binding.column_names:
            return {
                "expression": f"{alias}.*",
                "model_name": model_name,
                "reason": "wildcard_projection_not_supported",
            }
        return [
            (
                expanded_column,
                binding.column_lineage.get(expanded_column, ()),
            )
            for expanded_column in binding.column_names
            if binding.column_lineage.get(expanded_column)
        ]

    if binding.asset_name is not None:
        return (f"{binding.asset_name}.{column}",)

    source_columns = tuple(binding.column_lineage.get(column, ()))
    if not source_columns:
        return {
            "expression": f"{alias}.{column}",
            "model_name": model_name,
            "reason": "cte_column_not_resolved",
        }
    return source_columns


def _resolve_unqualified_reference_columns(
    identifier: str,
    *,
    relation_bindings: Mapping[str, _RelationBinding],
    model_name: str,
) -> tuple[str, ...] | dict[str, str]:
    """Resolve one bare identifier when it maps to a unique visible source."""

    candidates: dict[tuple[str, ...], tuple[str, ...]] = {}
    for binding in relation_bindings.values():
        resolved_columns = _binding_columns_for_identifier(binding, identifier)
        if resolved_columns:
            candidates.setdefault(tuple(resolved_columns), tuple(resolved_columns))

    if not candidates:
        return {
            "expression": identifier,
            "model_name": model_name,
            "reason": "unqualified_column_reference_not_resolved",
        }
    if len(candidates) > 1:
        return {
            "expression": identifier,
            "model_name": model_name,
            "reason": "unqualified_column_reference_ambiguous",
        }
    return next(iter(candidates.values()))


def _binding_columns_for_identifier(
    binding: _RelationBinding,
    identifier: str,
) -> tuple[str, ...]:
    """Return resolved source columns for one identifier within one binding."""

    if binding.asset_name is not None:
        if identifier not in binding.column_names:
            return ()
        return (f"{binding.asset_name}.{identifier}",)
    return tuple(binding.column_lineage.get(identifier, ()))


def _implicit_output_column(expression: str) -> str | None:
    """Infer an output column name when a projection omits `AS alias`."""

    references = list(_QUALIFIED_REFERENCE_RE.finditer(expression))
    if len(references) == 1 and references[0].group("column") != "*":
        return references[0].group("column")
    return None


__all__ = ["ColumnLineage", "CompiledModelLineage", "extract_compiled_model_lineage"]
