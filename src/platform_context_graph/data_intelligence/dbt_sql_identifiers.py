"""Identifier-scanning helpers for compiled dbt SQL lineage."""

from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"\b(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)\b")
_SINGLE_QUOTED_STRING_RE = re.compile(r"'(?:[^'\\\\]|\\\\.)*'")
_IGNORED_UNQUALIFIED_IDENTIFIERS = {
    "and",
    "as",
    "asc",
    "case",
    "cast",
    "coalesce",
    "count",
    "desc",
    "distinct",
    "else",
    "end",
    "false",
    "from",
    "group",
    "in",
    "is",
    "join",
    "left",
    "like",
    "limit",
    "lower",
    "not",
    "null",
    "on",
    "or",
    "order",
    "over",
    "partition",
    "by",
    "rows",
    "range",
    "preceding",
    "following",
    "current",
    "row",
    "right",
    "select",
    "sum",
    "then",
    "true",
    "upper",
    "when",
    "where",
    "with",
}


def unqualified_identifiers(
    expression: str,
    *,
    matched_identifiers: set[str],
) -> list[str]:
    """Return bare identifier candidates that still need lineage resolution."""

    sanitized_expression = _SINGLE_QUOTED_STRING_RE.sub(
        lambda match: " " * len(match.group(0)),
        expression,
    )
    identifiers: list[str] = []
    seen_identifiers: set[str] = set()
    for match in _IDENTIFIER_RE.finditer(sanitized_expression):
        identifier = match.group("identifier")
        lowered = identifier.lower()
        if (
            identifier in matched_identifiers
            or lowered in _IGNORED_UNQUALIFIED_IDENTIFIERS
            or identifier in seen_identifiers
        ):
            continue
        next_non_space = _next_non_space_character(sanitized_expression, match.end())
        if next_non_space == "(":
            continue
        seen_identifiers.add(identifier)
        identifiers.append(identifier)
    return identifiers


def _next_non_space_character(text: str, index: int) -> str | None:
    """Return the next non-whitespace character after one expression offset."""

    while index < len(text):
        if not text[index].isspace():
            return text[index]
        index += 1
    return None


__all__ = ["unqualified_identifiers"]
