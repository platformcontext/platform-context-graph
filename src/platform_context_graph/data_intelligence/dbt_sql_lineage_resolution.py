"""Reference-resolution helpers for compiled dbt SQL lineage."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_QUALIFIED_REFERENCE_RE = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\."
    r"(?P<column>\*|[A-Za-z_][A-Za-z0-9_]*)(?=[^A-Za-z0-9_]|$)"
)


def resolve_reference_columns(
    binding: Any | None,
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
        if getattr(binding, "asset_name", None) is not None:
            if not getattr(binding, "column_names", ()):
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
        if not getattr(binding, "column_names", ()):
            return {
                "expression": f"{alias}.*",
                "model_name": model_name,
                "reason": "wildcard_projection_not_supported",
            }
        return [
            (
                expanded_column,
                binding.column_lineage[expanded_column].source_columns,
            )
            for expanded_column in binding.column_names
            if binding.column_lineage.get(expanded_column)
        ]

    if getattr(binding, "asset_name", None) is not None:
        return (f"{binding.asset_name}.{column}",)

    source_lineage = binding.column_lineage.get(column)
    if source_lineage is None:
        return {
            "expression": f"{alias}.{column}",
            "model_name": model_name,
            "reason": "cte_column_not_resolved",
        }
    return source_lineage.source_columns


def resolve_unqualified_reference_columns(
    identifier: str,
    *,
    relation_bindings: Mapping[str, Any],
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


def _binding_columns_for_identifier(binding: Any, identifier: str) -> tuple[str, ...]:
    """Return resolved source columns for one identifier within one binding."""

    if getattr(binding, "asset_name", None) is not None:
        if identifier not in binding.column_names:
            return ()
        return (f"{binding.asset_name}.{identifier}",)
    item = binding.column_lineage.get(identifier)
    if item is None:
        return ()
    return item.source_columns


def implicit_output_column(expression: str) -> str | None:
    """Infer an output column name when a projection omits `AS alias`."""

    references = list(_QUALIFIED_REFERENCE_RE.finditer(expression))
    if len(references) == 1 and references[0].group("column") != "*":
        return references[0].group("column")
    return None


__all__ = [
    "implicit_output_column",
    "resolve_reference_columns",
    "resolve_unqualified_reference_columns",
]
