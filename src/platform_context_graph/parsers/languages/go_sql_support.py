"""SQL-aware helper extraction for Go parser results."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from platform_context_graph.utils.source_text import read_source_text

_FUNCTION_PATTERN = re.compile(
    r"func\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_]\w*)\s*\([^)]*\)\s*(?:\([^)]*\)|[^{\n]+)?\{",
    re.MULTILINE,
)
_SQL_CALL_PATTERN = re.compile(
    r"\.\s*(?P<call>ExecContext|Exec|QueryContext|QueryRowContext|QueryRow|QueryxContext|Queryx|GetContext|Get|SelectContext|Select)\s*\(",
    re.MULTILINE,
)
_TABLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "select",
        re.compile(
            r"\b(?:FROM|JOIN)\s+(?P<name>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)",
            re.IGNORECASE,
        ),
    ),
    (
        "update",
        re.compile(
            r"\bUPDATE\s+(?P<name>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)",
            re.IGNORECASE,
        ),
    ),
    (
        "insert",
        re.compile(
            r"\bINSERT\s+INTO\s+(?P<name>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)",
            re.IGNORECASE,
        ),
    ),
    (
        "delete",
        re.compile(
            r"\bDELETE\s+FROM\s+(?P<name>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)",
            re.IGNORECASE,
        ),
    ),
)


def extract_go_embedded_sql_queries(path: Path | str) -> list[dict[str, Any]]:
    """Return embedded SQL query hints extracted from one Go source file."""

    source = read_source_text(path)
    queries: list[dict[str, Any]] = []
    for (
        function_name,
        function_body,
        start_offset,
        function_line_number,
    ) in _iter_function_bodies(source):
        for body, body_offset in _iter_string_literals(function_body):
            api = _detect_api_for_offset(function_body, body_offset)
            if api is None:
                continue
            for operation, pattern in _TABLE_PATTERNS:
                match = pattern.search(body)
                if match is None:
                    continue
                queries.append(
                    {
                        "function_name": function_name,
                        "function_line_number": function_line_number,
                        "table_name": match.group("name"),
                        "operation": operation,
                        "line_number": _line_number_for_offset(
                            source,
                            start_offset + body_offset + match.start("name"),
                        ),
                        "api": api,
                    }
                )
                break
    return queries


def _iter_function_bodies(source: str) -> list[tuple[str, str, int, int]]:
    """Return function names, body text, and body start offsets from Go source."""

    functions: list[tuple[str, str, int, int]] = []
    for match in _FUNCTION_PATTERN.finditer(source):
        open_brace = source.find("{", match.start())
        close_brace = _matching_brace(source, open_brace)
        if open_brace < 0 or close_brace < 0:
            continue
        body_start = open_brace + 1
        functions.append(
            (
                match.group("name"),
                source[body_start:close_brace],
                body_start,
                _line_number_for_offset(source, match.start()),
            )
        )
    return functions


def _matching_brace(source: str, open_index: int) -> int:
    """Return the matching closing brace for a Go function body."""

    depth = 0
    for index in range(open_index, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _iter_string_literals(source: str) -> list[tuple[str, int]]:
    """Return string literal contents with offsets relative to ``source``."""

    literals: list[tuple[str, int]] = []
    index = 0
    while index < len(source):
        current = source[index]
        if current == "`":
            end = source.find("`", index + 1)
            if end < 0:
                break
            literals.append((source[index + 1 : end], index + 1))
            index = end + 1
            continue
        if current != '"':
            index += 1
            continue
        body_start = index + 1
        body: list[str] = []
        index += 1
        while index < len(source):
            current = source[index]
            if current == "\\" and index + 1 < len(source):
                body.append(current)
                body.append(source[index + 1])
                index += 2
                continue
            if current == '"':
                literals.append(("".join(body), body_start))
                index += 1
                break
            body.append(current)
            index += 1
        else:
            break
    return literals


def _detect_api(function_body: str) -> str | None:
    """Return the SQL client family used by one Go function body."""

    match = _SQL_CALL_PATTERN.search(function_body)
    if match is None:
        return None
    return _api_for_call_name(match.group("call"))


def _detect_api_for_offset(function_body: str, literal_offset: int) -> str | None:
    """Return the SQL client family closest to one string literal offset."""

    prior_body = function_body[:literal_offset]
    matches = list(_SQL_CALL_PATTERN.finditer(prior_body))
    if not matches:
        return None
    return _api_for_call_name(matches[-1].group("call"))


def _api_for_call_name(call_name: str) -> str:
    """Return the database client family implied by one call name."""

    return (
        "sqlx"
        if call_name
        in {
            "QueryxContext",
            "Queryx",
            "GetContext",
            "Get",
            "SelectContext",
            "Select",
        }
        else "database/sql"
    )


def _line_number_for_offset(source: str, offset: int) -> int:
    """Return the 1-based line number for a character offset."""

    return source[:offset].count("\n") + 1


__all__ = ["extract_go_embedded_sql_queries"]
