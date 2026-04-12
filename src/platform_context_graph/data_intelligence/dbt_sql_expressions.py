"""Expression-shape helpers for compiled dbt SQL lineage."""

from __future__ import annotations

import re

_BARE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUALIFIED_REFERENCE_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.(?:\*|[A-Za-z_][A-Za-z0-9_]*)$"
)
_DERIVED_EXPRESSION_REASON = "derived_expression_semantics_not_captured"


def expression_requires_partial_reporting(expression: str) -> bool:
    """Return whether a projection expression should report partial semantics."""

    normalized = _strip_wrapping_parentheses(expression.strip())
    if not normalized:
        return False
    if _BARE_IDENTIFIER_RE.fullmatch(normalized):
        return False
    if _QUALIFIED_REFERENCE_RE.fullmatch(normalized):
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


__all__ = ["derived_expression_gap", "expression_requires_partial_reporting"]
