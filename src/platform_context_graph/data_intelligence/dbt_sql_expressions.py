"""Expression-shape helpers for compiled dbt SQL lineage."""

from __future__ import annotations

import re

_BARE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUALIFIED_REFERENCE_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.(?:\*|[A-Za-z_][A-Za-z0-9_]*)$"
)
_FUNCTION_CALL_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<arguments>.*)\)$",
    re.DOTALL,
)
_SINGLE_QUOTED_LITERAL_RE = re.compile(r"^'(?:[^'\\\\]|\\\\.)*'$", re.DOTALL)
_NUMERIC_LITERAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
_DERIVED_EXPRESSION_REASON = "derived_expression_semantics_not_captured"
_SIMPLE_SCALAR_FUNCTIONS = {
    "upper",
    "lower",
    "trim",
    "ltrim",
    "rtrim",
}


def expression_requires_partial_reporting(expression: str) -> bool:
    """Return whether a projection expression should report partial semantics."""

    normalized = _strip_wrapping_parentheses(expression.strip())
    if not normalized:
        return False
    if _BARE_IDENTIFIER_RE.fullmatch(normalized):
        return False
    if _QUALIFIED_REFERENCE_RE.fullmatch(normalized):
        return False
    if _is_supported_scalar_wrapper(normalized):
        return False
    return True


def derived_expression_gap(*, expression: str, model_name: str) -> dict[str, str]:
    """Return the standardized unresolved-gap record for one derived expression."""

    return {
        "expression": expression.strip(),
        "model_name": model_name,
        "reason": _DERIVED_EXPRESSION_REASON,
    }


def _strip_wrapping_parentheses(expression: str) -> str:
    """Strip balanced outer parentheses from a projection expression."""

    normalized = expression.strip()
    while normalized.startswith("(") and normalized.endswith(")"):
        depth = 0
        balanced = True
        for index, character in enumerate(normalized):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(normalized) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            return normalized
        normalized = normalized[1:-1].strip()
    return normalized


def _is_supported_scalar_wrapper(expression: str) -> bool:
    """Return whether the expression is a supported one-column scalar wrapper."""

    match = _FUNCTION_CALL_RE.fullmatch(expression)
    if match is None:
        return False

    function_name = match.group("name").strip().lower()
    arguments = _split_top_level_arguments(match.group("arguments"))
    if function_name in _SIMPLE_SCALAR_FUNCTIONS and len(arguments) == 1:
        return _is_simple_reference_expression(arguments[0])
    if function_name == "coalesce" and len(arguments) >= 2:
        return _is_simple_reference_expression(arguments[0]) and all(
            _is_literal_expression(argument) for argument in arguments[1:]
        )
    return False


def _is_simple_reference_expression(expression: str) -> bool:
    """Return whether the expression is a direct supported column reference."""

    normalized = _strip_wrapping_parentheses(expression.strip())
    if not normalized:
        return False
    return bool(
        _BARE_IDENTIFIER_RE.fullmatch(normalized)
        or _QUALIFIED_REFERENCE_RE.fullmatch(normalized)
    )


def _is_literal_expression(expression: str) -> bool:
    """Return whether the expression is a supported literal fallback."""

    normalized = _strip_wrapping_parentheses(expression.strip())
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered in {"null", "true", "false"}:
        return True
    if _SINGLE_QUOTED_LITERAL_RE.fullmatch(normalized):
        return True
    return bool(_NUMERIC_LITERAL_RE.fullmatch(normalized))


def _split_top_level_arguments(arguments: str) -> list[str]:
    """Split one function-argument list on top-level commas."""

    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_single_quote = False

    for character in arguments:
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


__all__ = ["derived_expression_gap", "expression_requires_partial_reporting"]
