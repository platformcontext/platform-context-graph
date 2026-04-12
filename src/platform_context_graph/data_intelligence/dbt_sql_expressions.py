"""Expression-shape helpers for compiled dbt SQL lineage."""

from __future__ import annotations

import re

from .dbt_sql_identifiers import unqualified_identifiers

_BARE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUALIFIED_REFERENCE_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.(?:\*|[A-Za-z_][A-Za-z0-9_]*)$"
)
_QUALIFIED_REFERENCE_SCAN_RE = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\."
    r"(?P<column>[A-Za-z_][A-Za-z0-9_]*)(?=[^A-Za-z0-9_]|$)"
)
_FUNCTION_CALL_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<arguments>.*)\)$",
    re.DOTALL,
)
_FUNCTION_CALL_SCAN_RE = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
)
_SINGLE_QUOTED_LITERAL_RE = re.compile(r"^'(?:[^'\\\\]|\\\\.)*'$", re.DOTALL)
_SINGLE_QUOTED_LITERAL_SCAN_RE = re.compile(r"'(?:[^'\\\\]|\\\\.)*'", re.DOTALL)
_NUMERIC_LITERAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
_NUMERIC_LITERAL_SCAN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[+-]?(?:\d+(?:\.\d+)?|\.\d+))(?![A-Za-z0-9_])"
)
_TYPE_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_CASE_EXPRESSION_RE = re.compile(r"^case\b.*\bend$", re.IGNORECASE | re.DOTALL)
_CASE_KEYWORD_RE = re.compile(
    r"\b(?:case|when|then|else|end|is|null|and|or|not|in|like|between|true|false)\b",
    re.IGNORECASE,
)
_AGGREGATE_EXPRESSION_REASON = "aggregate_expression_semantics_not_captured"
_DERIVED_EXPRESSION_REASON = "derived_expression_semantics_not_captured"
_MULTI_INPUT_EXPRESSION_REASON = "multi_input_expression_semantics_not_captured"
_AGGREGATE_FUNCTIONS = {
    "avg",
    "count",
    "max",
    "min",
    "sum",
}
_SIMPLE_SCALAR_FUNCTIONS = {
    "upper",
    "lower",
    "trim",
    "ltrim",
    "rtrim",
}
_LITERAL_PARAMETER_SCALAR_FUNCTIONS = {
    "date_trunc",
}


def expression_requires_partial_reporting(expression: str) -> bool:
    """Return whether a projection expression should report partial semantics."""

    return expression_partial_reason(expression) is not None


def expression_transform_metadata(expression: str) -> dict[str, str] | None:
    """Return transform metadata for supported non-identity expressions."""

    normalized = _strip_wrapping_parentheses(expression.strip())
    if not normalized:
        return None
    if _BARE_IDENTIFIER_RE.fullmatch(normalized):
        return None
    if _QUALIFIED_REFERENCE_RE.fullmatch(normalized):
        return None

    cast_expression = _supported_cast_expression(normalized)
    if cast_expression is not None:
        return {
            "transform_kind": "cast",
            "transform_expression": normalized,
        }
    if _is_supported_case_expression(normalized):
        return {
            "transform_kind": "case",
            "transform_expression": normalized,
        }
    if _is_supported_arithmetic_expression(normalized):
        return {
            "transform_kind": "arithmetic",
            "transform_expression": normalized,
        }

    match = _FUNCTION_CALL_RE.fullmatch(normalized)
    if match is None:
        return None

    function_name = match.group("name").strip().lower()
    arguments = _split_top_level_arguments(match.group("arguments"))
    if function_name in _SIMPLE_SCALAR_FUNCTIONS and len(arguments) == 1:
        if _is_simple_reference_expression(arguments[0]):
            return {
                "transform_kind": function_name,
                "transform_expression": normalized,
            }
        return None
    if function_name == "coalesce" and len(arguments) >= 2:
        if _is_simple_reference_expression(arguments[0]) and all(
            _is_literal_expression(argument) for argument in arguments[1:]
        ):
            return {
                "transform_kind": "coalesce",
                "transform_expression": normalized,
            }
        return None
    if function_name in _LITERAL_PARAMETER_SCALAR_FUNCTIONS and len(arguments) >= 2:
        reference_arguments = [
            argument
            for argument in arguments
            if _is_simple_reference_expression(argument)
        ]
        if len(reference_arguments) != 1:
            return None
        if all(
            _is_simple_reference_expression(argument)
            or _is_literal_expression(argument)
            for argument in arguments
        ):
            return {
                "transform_kind": function_name,
                "transform_expression": normalized,
            }
    return None


def expression_partial_reason(expression: str) -> str | None:
    """Return a specific partial-lineage reason when the expression is unsupported."""

    normalized = _strip_wrapping_parentheses(expression.strip())
    if not normalized:
        return None
    if _BARE_IDENTIFIER_RE.fullmatch(normalized):
        return None
    if _QUALIFIED_REFERENCE_RE.fullmatch(normalized):
        return None
    if _is_supported_case_expression(normalized):
        return None
    if _is_supported_arithmetic_expression(normalized):
        return None
    if _is_supported_scalar_wrapper(normalized):
        return None
    function_reason = _unsupported_function_reason(normalized)
    if function_reason is not None:
        return function_reason
    return _DERIVED_EXPRESSION_REASON


def expression_ignored_identifiers(expression: str) -> set[str]:
    """Return extra bare identifiers that should be ignored for this expression."""

    cast_expression = _supported_cast_expression(expression)
    if cast_expression is None:
        return set()
    return {
        match.group(0)
        for match in _TYPE_IDENTIFIER_RE.finditer(cast_expression[1])
    }


def derived_expression_gap(
    *,
    expression: str,
    model_name: str,
    reason: str,
) -> dict[str, str]:
    """Return the standardized unresolved-gap record for one derived expression."""

    return {
        "expression": expression.strip(),
        "model_name": model_name,
        "reason": reason,
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

    if _supported_cast_expression(expression) is not None:
        return True

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
    if function_name in _LITERAL_PARAMETER_SCALAR_FUNCTIONS and len(arguments) >= 2:
        reference_arguments = [
            argument for argument in arguments if _is_simple_reference_expression(argument)
        ]
        if len(reference_arguments) != 1:
            return False
        return all(
            _is_simple_reference_expression(argument)
            or _is_literal_expression(argument)
            for argument in arguments
        )
    return False


def _is_supported_case_expression(expression: str) -> bool:
    """Return whether the expression is a supported one-column CASE transform."""

    if _CASE_EXPRESSION_RE.fullmatch(expression) is None:
        return False
    if _has_unsupported_function_call(expression):
        return False
    references = _simple_reference_tokens(expression)
    if len(references) != 1:
        return False

    collapsed = _collapsed_shape(
        expression,
        references=references,
        strip_case_keywords=True,
    )
    return re.fullmatch(r"[\s()=<>!,+\-*/%]*", collapsed) is not None


def _is_supported_arithmetic_expression(expression: str) -> bool:
    """Return whether the expression is a supported one-column arithmetic transform."""

    if not any(operator in expression for operator in ("+", "-", "*", "/", "%")):
        return False
    if _has_unsupported_function_call(expression):
        return False
    references = _simple_reference_tokens(expression)
    if len(references) != 1:
        return False

    collapsed = _collapsed_shape(expression, references=references)
    return re.fullmatch(r"[\s()+\-*/%]*", collapsed) is not None


def _supported_cast_expression(expression: str) -> tuple[str, str] | None:
    """Return the cast value/type when the CAST expression is supported."""

    match = _FUNCTION_CALL_RE.fullmatch(expression)
    if match is None or match.group("name").strip().lower() != "cast":
        return None

    value_expression, type_expression = _split_cast_arguments(match.group("arguments"))
    if value_expression is None or type_expression is None:
        return None
    if not _is_simple_reference_expression(value_expression):
        return None
    if not type_expression.strip():
        return None
    return value_expression, type_expression


def _unsupported_function_reason(expression: str) -> str | None:
    """Return a more specific unsupported-function reason when possible."""

    match = _FUNCTION_CALL_RE.fullmatch(expression)
    if match is None:
        return None

    function_name = match.group("name").strip().lower()
    if function_name in _AGGREGATE_FUNCTIONS:
        return _AGGREGATE_EXPRESSION_REASON

    arguments = _split_top_level_arguments(match.group("arguments"))
    reference_count = sum(
        1 for argument in arguments if _is_simple_reference_expression(argument)
    )
    if reference_count > 1:
        return _MULTI_INPUT_EXPRESSION_REASON
    return None


def _simple_reference_tokens(expression: str) -> tuple[str, ...]:
    """Return unique simple reference tokens used in one expression."""

    matched_identifiers: set[str] = set()
    tokens: list[str] = []
    seen_tokens: set[str] = set()
    for match in _QUALIFIED_REFERENCE_SCAN_RE.finditer(expression):
        token = match.group(0)
        matched_identifiers.add(match.group("alias"))
        matched_identifiers.add(match.group("column"))
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        tokens.append(token)
    for identifier in unqualified_identifiers(
        expression,
        matched_identifiers=matched_identifiers,
    ):
        if identifier in seen_tokens:
            continue
        seen_tokens.add(identifier)
        tokens.append(identifier)
    return tuple(tokens)


def _has_unsupported_function_call(expression: str) -> bool:
    """Return whether the expression contains a nested function call."""

    for match in _FUNCTION_CALL_SCAN_RE.finditer(expression):
        if match.group("name").strip().lower() in {
            "and",
            "case",
            "else",
            "end",
            "in",
            "is",
            "not",
            "or",
            "then",
            "when",
        }:
            continue
        return True
    return False


def _collapsed_shape(
    expression: str,
    *,
    references: tuple[str, ...],
    strip_case_keywords: bool = False,
) -> str:
    """Return one expression with references and literals reduced to shape tokens."""

    sanitized = _SINGLE_QUOTED_LITERAL_SCAN_RE.sub("0", expression)
    sanitized = _NUMERIC_LITERAL_SCAN_RE.sub("0", sanitized)
    sanitized = _replace_reference_tokens(sanitized, references)
    if strip_case_keywords:
        sanitized = _CASE_KEYWORD_RE.sub(" ", sanitized)
    return sanitized.replace("REF", "").replace("0", "")


def _replace_reference_tokens(expression: str, references: tuple[str, ...]) -> str:
    """Replace simple reference tokens with a uniform placeholder."""

    sanitized = expression
    for token in references:
        sanitized = re.sub(rf"\b{re.escape(token)}\b", "REF", sanitized)
    return sanitized


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


def _split_cast_arguments(arguments: str) -> tuple[str | None, str | None]:
    """Split one CAST body into value and type expressions."""

    depth = 0
    in_single_quote = False
    lower_arguments = arguments.lower()

    for index, character in enumerate(arguments):
        if character == "'" and (index == 0 or arguments[index - 1] != "\\"):
            in_single_quote = not in_single_quote
            continue
        if in_single_quote:
            continue
        if character == "(":
            depth += 1
            continue
        if character == ")" and depth > 0:
            depth -= 1
            continue
        if depth != 0:
            continue
        if lower_arguments[index : index + 4] != " as ":
            continue
        value_expression = arguments[:index].strip()
        type_expression = arguments[index + 4 :].strip()
        return value_expression, type_expression
    return None, None


__all__ = [
    "derived_expression_gap",
    "expression_ignored_identifiers",
    "expression_partial_reason",
    "expression_transform_metadata",
    "expression_requires_partial_reporting",
]
