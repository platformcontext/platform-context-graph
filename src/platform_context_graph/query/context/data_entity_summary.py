"""Persona-friendly summaries for data-entity context responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..data_lineage_evidence import summarize_lineage_edges

_DOWNSTREAM_COUNT_FIELDS = {
    "analytics_model": "analytics_model_count",
    "data_asset": "data_asset_count",
    "data_column": "data_column_count",
    "query_execution": "query_execution_count",
    "dashboard_asset": "dashboard_asset_count",
    "data_quality_check": "data_quality_check_count",
}
_DIRECT_RELATIONSHIP_FIELDS = {
    "COMPILES_TO": "compiles_to",
    "ASSET_DERIVES_FROM": "asset_derives_from",
    "COLUMN_DERIVES_FROM": "column_derives_from",
    "RUNS_QUERY_AGAINST": "runs_query_against",
    "POWERS": "powers",
    "ASSERTS_QUALITY_ON": "asserts_quality_on",
    "OWNS": "owns",
    "DECLARES_CONTRACT_FOR": "declares_contract_for",
}
_ENTITY_LABELS = {
    "analytics_model": "analytics model",
    "data_asset": "data asset",
    "data_column": "data column",
    "query_execution": "query execution",
    "dashboard_asset": "dashboard asset",
    "data_quality_check": "data quality check",
}
_IMPACT_SAMPLE_PRIORITY = {
    "dashboard_asset": 0,
    "data_quality_check": 1,
    "data_column": 2,
    "data_asset": 3,
    "analytics_model": 4,
    "query_execution": 5,
}


def build_data_entity_summary(
    entity: Mapping[str, Any],
    *,
    edges: list[dict[str, Any]],
    change_surface: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a persona-friendly summary for one data entity.

    Args:
        entity: Data-entity snapshot.
        edges: Direct graph edges connected to the entity.
        change_surface: Change-surface payload for the same entity.

    Returns:
        Structured data summary suitable for entity-context responses.
    """

    lineage_evidence = summarize_lineage_edges(edges)
    downstream_counts = _downstream_counts(change_surface)
    direct_relationship_counts = _direct_relationship_counts(edges)
    sample_impacted_entities = _sample_impacted_entities(change_surface)
    ownership = {
        "owner_names": _string_list(entity.get("owner_names")),
        "owner_teams": _string_list(entity.get("owner_teams")),
    }
    contracts = {
        "contract_names": _string_list(entity.get("contract_names")),
        "contract_levels": _string_list(entity.get("contract_levels")),
        "change_policies": _string_list(entity.get("change_policies")),
    }
    governance = {
        "sensitivity": _optional_string(entity.get("sensitivity")),
        "is_protected": bool(entity.get("is_protected")),
        "protection_kind": _optional_string(entity.get("protection_kind")),
    }
    change_classification = dict(
        (change_surface or {}).get("target_change_classification") or {}
    )
    highest_downstream_classification = str(
        ((change_surface or {}).get("classification_summary") or {}).get("highest")
        or "informational"
    ).strip()
    return {
        "summary": _summary_text(
            entity=entity,
            lineage_evidence=lineage_evidence,
            downstream_counts=downstream_counts,
            ownership=ownership,
            governance=governance,
            change_classification=change_classification,
        ),
        "lineage_evidence": lineage_evidence,
        "change_classification": change_classification,
        "highest_downstream_classification": highest_downstream_classification,
        "downstream_counts": downstream_counts,
        "direct_relationship_counts": direct_relationship_counts,
        "sample_impacted_entities": sample_impacted_entities,
        "ownership": ownership,
        "contracts": contracts,
        "governance": governance,
    }


def _downstream_counts(change_surface: Mapping[str, Any] | None) -> dict[str, int]:
    """Return downstream impacted-entity counts grouped by canonical type."""

    counts = {field_name: 0 for field_name in _DOWNSTREAM_COUNT_FIELDS.values()}
    for item in list((change_surface or {}).get("impacted") or []):
        entity = dict(item.get("entity") or {})
        entity_type = str(entity.get("type") or "").strip()
        field_name = _DOWNSTREAM_COUNT_FIELDS.get(entity_type)
        if field_name is None:
            continue
        counts[field_name] += 1
    return counts


def _direct_relationship_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    """Return direct edge counts grouped by user-facing field name."""

    counts = {field_name: 0 for field_name in _DIRECT_RELATIONSHIP_FIELDS.values()}
    for edge in edges:
        relationship_type = str(edge.get("type") or "").strip()
        field_name = _DIRECT_RELATIONSHIP_FIELDS.get(relationship_type)
        if field_name is None:
            continue
        counts[field_name] += 1
    return counts


def _sample_impacted_entities(
    change_surface: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return a stable sample of downstream impacted entities."""

    impacted = []
    for item in list((change_surface or {}).get("impacted") or []):
        entity = dict(item.get("entity") or {})
        entity_id = str(entity.get("id") or "").strip()
        entity_type = str(entity.get("type") or "").strip()
        if not entity_id or not entity_type:
            continue
        impacted.append(entity)
    impacted.sort(
        key=lambda entity: (
            _IMPACT_SAMPLE_PRIORITY.get(str(entity.get("type") or "").strip(), 99),
            str(entity.get("name") or entity.get("id") or "").lower(),
        )
    )
    return impacted[:5]


def _summary_text(
    *,
    entity: Mapping[str, Any],
    lineage_evidence: dict[str, Any] | None,
    downstream_counts: Mapping[str, int],
    ownership: Mapping[str, list[str]],
    governance: Mapping[str, Any],
    change_classification: Mapping[str, Any],
) -> str:
    """Return a compact user-facing summary sentence."""

    entity_type = str(entity.get("type") or "").strip()
    entity_label = _ENTITY_LABELS.get(entity_type, entity_type.replace("_", " "))
    classification = str(
        change_classification.get("primary") or "informational"
    ).strip()
    parts = [
        f"{classification.replace('-', ' ').capitalize()} {entity_label} "
        f"with {_downstream_summary_text(downstream_counts)}"
    ]
    if lineage_evidence is not None:
        parts.append(f"lineage evidence is {lineage_evidence['status']}")
    owner_names = list(ownership.get("owner_names") or [])
    owner_teams = list(ownership.get("owner_teams") or [])
    owner_labels = owner_names or owner_teams
    if owner_labels:
        parts.append(f"owners: {', '.join(owner_labels)}")
    if bool(governance.get("is_protected")):
        protected_as = str(governance.get("protection_kind") or "protected").strip()
        parts.append(f"protected as {protected_as}")
    sensitivity = _optional_string(governance.get("sensitivity"))
    if sensitivity:
        parts.append(f"sensitivity: {sensitivity}")
    return "; ".join(parts) + "."


def _downstream_summary_text(counts: Mapping[str, int]) -> str:
    """Return a compact downstream-dependent summary."""

    total = sum(int(value or 0) for value in counts.values())
    if total == 0:
        return "no downstream consumers indexed"

    labels = [
        _count_label(int(counts.get("dashboard_asset_count") or 0), "dashboard"),
        _count_label(
            int(counts.get("data_quality_check_count") or 0),
            "quality check",
        ),
        _count_label(int(counts.get("data_column_count") or 0), "data column"),
        _count_label(int(counts.get("data_asset_count") or 0), "data asset"),
        _count_label(int(counts.get("query_execution_count") or 0), "query execution"),
        _count_label(int(counts.get("analytics_model_count") or 0), "analytics model"),
    ]
    details = [label for label in labels if label]
    if not details:
        return f"{total} downstream dependent{'' if total == 1 else 's'}"
    return (
        f"{total} downstream dependent{'' if total == 1 else 's'} "
        f"({', '.join(details)})"
    )


def _count_label(count: int, label: str) -> str:
    """Return one compact count label."""

    if count <= 0:
        return ""
    return f"{count} {label}{'' if count == 1 else 's'}"


def _optional_string(value: Any) -> str | None:
    """Return a stripped string or ``None`` when empty."""

    normalized = str(value or "").strip()
    return normalized or None


def _string_list(value: Any) -> list[str]:
    """Return a normalized list of non-empty strings."""

    if not isinstance(value, list):
        return []
    return [normalized for item in value if (normalized := str(item).strip())]


__all__ = ["build_data_entity_summary"]
