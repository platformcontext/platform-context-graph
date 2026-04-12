"""Helpers for classifying data-intelligence change risk."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_CLASSIFICATION_ORDER = (
    "governance-sensitive",
    "breaking",
    "quality-risk",
    "additive",
    "informational",
)
_CLASSIFICATION_RANK = {
    classification: index for index, classification in enumerate(_CLASSIFICATION_ORDER)
}
_HIGH_RISK_SENSITIVITIES = frozenset(
    {"pii", "phi", "pci", "secret", "restricted", "sensitive"}
)
_NON_PROPAGATING_RELATIONSHIP_TYPES = frozenset(
    {
        "CONTAINS",
        "REPO_CONTAINS",
        "INSTANCE_OF",
        "DEFINES",
        "OWNS",
        "DECLARES_CONTRACT_FOR",
        "MASKS",
    }
)


def classify_data_change(entity: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized change classification for one entity snapshot.

    Args:
        entity: Raw entity snapshot from the impact graph store.

    Returns:
        User-facing change classification with a primary label, contributing
        signals, and concise reasoning strings.
    """

    signals: list[str] = []
    reasons: list[str] = []
    entity_type = str(entity.get("type") or "").strip()

    if entity_type == "data_quality_check":
        signals.append("quality-risk")
        severity = str(entity.get("severity") or "unknown").strip()
        status = str(entity.get("status") or "unknown").strip()
        reasons.append(
            f"Downstream quality check status is {status} with {severity} severity."
        )

    if entity_type in {"data_asset", "data_column"}:
        sensitivity = str(entity.get("sensitivity") or "").strip()
        if bool(entity.get("is_protected")) or sensitivity.lower() in _HIGH_RISK_SENSITIVITIES:
            signals.append("governance-sensitive")
            if bool(entity.get("is_protected")):
                protection_kind = str(entity.get("protection_kind") or "protected").strip()
                reasons.append(
                    f"Protected-field metadata marks this entity as {protection_kind}."
                )
            elif sensitivity:
                reasons.append(
                    f"Sensitivity metadata marks this entity as {sensitivity}."
                )

        policies = _string_list(entity.get("change_policies"))
        if "breaking" in policies:
            signals.append("breaking")
            reasons.append("Contract change policy marks this entity as breaking.")
        elif "additive" in policies:
            signals.append("additive")
            reasons.append("Contract change policy marks this entity as additive.")

    if not signals:
        signals = ["informational"]
        reasons = ["No quality or governance risk metadata matched this entity."]

    primary = min(signals, key=_CLASSIFICATION_RANK.__getitem__)
    ordered_signals = sorted(set(signals), key=_CLASSIFICATION_RANK.__getitem__)
    return {
        "primary": primary,
        "signals": ordered_signals,
        "reasons": _unique_strings(reasons),
    }


def summarize_data_change_classifications(
    classifications: Iterable[Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Aggregate multiple change classifications into one summary."""

    counts = {classification: 0 for classification in _CLASSIFICATION_ORDER}
    highest = "informational"
    for item in classifications:
        if not isinstance(item, Mapping):
            continue
        primary = str(item.get("primary") or "informational").strip()
        if primary not in counts:
            continue
        counts[primary] += 1
        if _CLASSIFICATION_RANK[primary] < _CLASSIFICATION_RANK[highest]:
            highest = primary
    return {
        "highest": highest,
        "counts": counts,
    }


def classify_impacted_data_change(
    entity: Mapping[str, Any],
    *,
    path: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a path-aware change classification for one impacted entity."""

    classification = classify_data_change(entity)
    relationship_types = {
        str(hop.get("type") or "").strip()
        for hop in list((path or {}).get("hops") or [])
        if str(hop.get("type") or "").strip()
    }
    if (
        relationship_types
        and relationship_types <= _NON_PROPAGATING_RELATIONSHIP_TYPES
        and classification["primary"] != "informational"
    ):
        return {
            "primary": "informational",
            "signals": ["informational"],
            "reasons": [
                "Only structural or governance-overlay links connect this entity to the source change."
            ],
        }
    return classification


def _string_list(value: Any) -> list[str]:
    """Return a normalized list of non-empty strings."""

    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_strings(values: Iterable[str]) -> list[str]:
    """Return ordered unique strings."""

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


__all__ = [
    "classify_data_change",
    "classify_impacted_data_change",
    "summarize_data_change_classifications",
]
