"""Transform-metadata helpers for compiled dbt SQL lineage."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .dbt_sql_expressions import expression_transform_metadata

_QUALIFIED_REFERENCE_RE = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\."
    r"(?P<column>\*|[A-Za-z_][A-Za-z0-9_]*)(?=[^A-Za-z0-9_]|$)"
)
_BARE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def transform_metadata_for_projection(
    expression: str,
    *,
    relation_bindings: Mapping[str, Any],
) -> dict[str, str]:
    """Return direct or propagated transform metadata for one projection."""

    metadata = expression_transform_metadata(expression)
    if metadata is not None:
        return metadata
    propagated = _propagated_transform_metadata(
        expression,
        relation_bindings=relation_bindings,
    )
    if propagated is not None:
        return propagated
    return {}


def _propagated_transform_metadata(
    expression: str,
    *,
    relation_bindings: Mapping[str, Any],
) -> dict[str, str] | None:
    """Return transform metadata inherited from a transformed CTE column."""

    normalized = expression.strip()
    qualified_match = _QUALIFIED_REFERENCE_RE.fullmatch(normalized)
    if qualified_match is not None and qualified_match.group("column") != "*":
        binding = relation_bindings.get(qualified_match.group("alias"))
        return _binding_transform_metadata(binding, qualified_match.group("column"))

    if _BARE_IDENTIFIER_RE.fullmatch(normalized) is None:
        return None

    candidates: dict[tuple[str, str], dict[str, str]] = {}
    for binding in relation_bindings.values():
        metadata = _binding_transform_metadata(binding, normalized)
        if metadata is None:
            continue
        key = (metadata["transform_kind"], metadata["transform_expression"])
        candidates.setdefault(key, metadata)
    if len(candidates) != 1:
        return None
    return next(iter(candidates.values()))


def _binding_transform_metadata(
    binding: Any | None,
    column_name: str,
) -> dict[str, str] | None:
    """Return transform metadata for one CTE column binding when present."""

    if binding is None or getattr(binding, "asset_name", None) is not None:
        return None
    item = getattr(binding, "column_lineage", {}).get(column_name)
    transform_kind = getattr(item, "transform_kind", None)
    transform_expression = getattr(item, "transform_expression", None)
    if transform_kind is None or transform_expression is None:
        return None
    return {
        "transform_kind": transform_kind,
        "transform_expression": transform_expression,
    }


__all__ = ["transform_metadata_for_projection"]
