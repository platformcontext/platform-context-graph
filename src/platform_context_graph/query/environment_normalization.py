"""Shared environment normalization helpers for story and context shaping."""

from __future__ import annotations

import re
from typing import Any

_CANONICAL_ENVIRONMENT_KEYS = {
    "dev": "dev",
    "development": "dev",
    "qa": "qa",
    "test": "test",
    "stage": "staging",
    "staging": "staging",
    "prod": "prod",
    "production": "prod",
}
_PRESERVED_ENVIRONMENT_LABEL = re.compile(
    r"^(?:bg|ops|prod|qa|stage|staging|dev|test)-[a-z0-9]+$"
)
_TRIMMABLE_PREFIXES = ("values-", "value-", "env-", "environment-", "namespace-")


def normalized_environment_value(value: Any) -> str:
    """Return one normalized environment string."""

    return str(value or "").strip().lower()


def canonical_environment_key(value: Any) -> str:
    """Return the canonical comparison key for one environment-like value."""

    normalized = normalized_environment_value(value)
    if not normalized:
        return ""
    if normalized in _CANONICAL_ENVIRONMENT_KEYS:
        return _CANONICAL_ENVIRONMENT_KEYS[normalized]
    mapped_tokens = {
        _CANONICAL_ENVIRONMENT_KEYS[token]
        for token in re.split(r"[^a-z0-9]+", normalized)
        if token in _CANONICAL_ENVIRONMENT_KEYS
    }
    if len(mapped_tokens) == 1:
        return next(iter(mapped_tokens))
    return normalized


def environments_match(left: Any, right: Any) -> bool:
    """Return whether two environment-like values describe the same family."""

    left_key = canonical_environment_key(left)
    right_key = canonical_environment_key(right)
    return bool(left_key and right_key and left_key == right_key)


def preferred_environment_label(values: list[Any]) -> str:
    """Return the most specific display label from one environment family."""

    best_label = ""
    best_score = -1
    for value in values:
        normalized = normalized_environment_value(value)
        if not normalized:
            continue
        score = _environment_specificity(normalized)
        if score > best_score:
            best_label = normalized
            best_score = score
    return best_label


def ordered_unique_environment_names(values: list[Any]) -> list[str]:
    """Return ordered unique environment names deduped by canonical family."""

    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for value in values:
        normalized = normalized_environment_value(value)
        if not normalized:
            continue
        key = canonical_environment_key(normalized)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(normalized)
    return [
        preferred_environment_label(groups[key]) or groups[key][0]
        for key in order
        if groups.get(key)
    ]


def infer_environment_label(value: Any) -> str | None:
    """Infer an environment label from one path, file, or namespace token."""

    normalized = normalized_environment_value(value)
    if not normalized:
        return None
    for candidate in _candidate_environment_values(normalized):
        if candidate in _CANONICAL_ENVIRONMENT_KEYS:
            return candidate
        if _PRESERVED_ENVIRONMENT_LABEL.match(candidate):
            return candidate
    for candidate in _candidate_environment_values(normalized):
        canonical = canonical_environment_key(candidate)
        if canonical and canonical != candidate:
            return canonical
    return None


def _candidate_environment_values(value: str) -> list[str]:
    """Return candidate environment tokens derived from one raw value."""

    candidates = [value]
    for prefix in _TRIMMABLE_PREFIXES:
        if value.startswith(prefix):
            candidates.append(value[len(prefix) :])

    tokens = [token for token in re.split(r"[^a-z0-9]+", value) if token]
    if len(tokens) >= 2:
        candidates.append("-".join(tokens[-2:]))
    if tokens:
        candidates.append(tokens[-1])

    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _environment_specificity(value: str) -> int:
    """Return a display-priority score for one environment label."""

    score = 0
    if _PRESERVED_ENVIRONMENT_LABEL.match(value):
        score += 30
    if canonical_environment_key(value) != value:
        score += 10
    if "-" in value or "_" in value:
        score += 4
    score += min(len(value), 20)
    return score
