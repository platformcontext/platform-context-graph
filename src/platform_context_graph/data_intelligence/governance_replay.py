"""Governance replay normalization for vendor-neutral ownership overlays."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


class GovernanceReplayPlugin:
    """Normalize governance replay payloads into owners, contracts, and overlays."""

    name = "governance-replay"
    category = "governance"
    replay_fixture_groups = ("governance_replay_comprehensive",)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one governance replay payload into graph-ready records."""

        data_owners: list[dict[str, Any]] = []
        data_contracts: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        annotations_by_target: dict[str, dict[str, Any]] = {}
        workspace = str(payload.get("metadata", {}).get("workspace") or "default")

        for owner in _as_sequence(payload.get("owners")):
            owner_record = _owner_record(owner, workspace=workspace)
            data_owners.append(owner_record)
            for asset_name in _as_string_sequence(owner.get("owns_assets")):
                relationships.append(
                    _relationship_record(
                        relationship_type="OWNS",
                        source_name=owner_record["name"],
                        target_name=asset_name,
                    )
                )
                _update_annotation(
                    annotations_by_target,
                    target_name=asset_name,
                    target_kind="DataAsset",
                    owner_name=owner_record["name"],
                    owner_team=owner_record.get("team"),
                )
            for column_name in _as_string_sequence(owner.get("owns_columns")):
                relationships.append(
                    _relationship_record(
                        relationship_type="OWNS",
                        source_name=owner_record["name"],
                        target_name=column_name,
                    )
                )
                _update_annotation(
                    annotations_by_target,
                    target_name=column_name,
                    target_kind="DataColumn",
                    owner_name=owner_record["name"],
                    owner_team=owner_record.get("team"),
                )

        for contract in _as_sequence(payload.get("contracts")):
            contract_record = _contract_record(contract, workspace=workspace)
            data_contracts.append(contract_record)
            for asset_name in _as_string_sequence(contract.get("targets_assets")):
                relationships.append(
                    _relationship_record(
                        relationship_type="DECLARES_CONTRACT_FOR",
                        source_name=contract_record["name"],
                        target_name=asset_name,
                    )
                )
                _update_annotation(
                    annotations_by_target,
                    target_name=asset_name,
                    target_kind="DataAsset",
                    contract_name=contract_record["name"],
                    contract_level=contract_record.get("contract_level"),
                    change_policy=contract_record.get("change_policy"),
                )
            for column in _as_target_columns(contract.get("targets_columns")):
                target_name = column["name"]
                relationships.append(
                    _relationship_record(
                        relationship_type="DECLARES_CONTRACT_FOR",
                        source_name=contract_record["name"],
                        target_name=target_name,
                    )
                )
                _update_annotation(
                    annotations_by_target,
                    target_name=target_name,
                    target_kind="DataColumn",
                    contract_name=contract_record["name"],
                    contract_level=contract_record.get("contract_level"),
                    change_policy=contract_record.get("change_policy"),
                    sensitivity=column.get("sensitivity"),
                    is_protected=column.get("is_protected"),
                    protection_kind=column.get("protection_kind"),
                )
                if column.get("is_protected"):
                    relationships.append(
                        _relationship_record(
                            relationship_type="MASKS",
                            source_name=contract_record["name"],
                            target_name=target_name,
                            sensitivity=column.get("sensitivity"),
                            protection_kind=column.get("protection_kind"),
                        )
                    )

        data_owners.sort(key=lambda item: item["name"])
        data_contracts.sort(key=lambda item: item["name"])
        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )
        governance_annotations = sorted(
            (_finalize_annotation(annotation) for annotation in annotations_by_target.values()),
            key=lambda item: (item["target_kind"], item["target_name"]),
        )
        return {
            "data_owners": data_owners,
            "data_contracts": data_contracts,
            "relationships": relationships,
            "governance_annotations": governance_annotations,
            "coverage": {
                "confidence": 1.0,
                "state": "complete",
                "unresolved_references": [],
            },
        }


def _relationship_record(
    *,
    relationship_type: str,
    source_name: str,
    target_name: str,
    sensitivity: str | None = None,
    protection_kind: str | None = None,
) -> dict[str, Any]:
    """Return one normalized governance relationship row."""

    record = {
        "type": relationship_type,
        "source_name": source_name,
        "target_name": target_name,
        "confidence": 1.0,
    }
    if sensitivity:
        record["sensitivity"] = sensitivity
    if protection_kind:
        record["protection_kind"] = protection_kind
    return record


def _owner_record(owner: Mapping[str, Any], *, workspace: str) -> dict[str, Any]:
    """Return one normalized data-owner record."""

    owner_id = str(owner.get("owner_id") or "").strip() or "data-owner"
    return {
        "name": str(owner.get("name") or owner_id).strip(),
        "line_number": 1,
        "path": str(owner.get("path") or ""),
        "workspace": workspace,
        "team": str(owner.get("team") or "").strip(),
    }


def _contract_record(contract: Mapping[str, Any], *, workspace: str) -> dict[str, Any]:
    """Return one normalized data-contract record."""

    contract_id = str(contract.get("contract_id") or "").strip() or "data-contract"
    return {
        "name": str(contract.get("name") or contract_id).strip(),
        "line_number": 1,
        "path": str(contract.get("path") or ""),
        "workspace": workspace,
        "contract_level": str(contract.get("contract_level") or "unspecified").strip(),
        "change_policy": str(contract.get("change_policy") or "unknown").strip(),
    }


def _as_sequence(value: Any) -> Sequence[Mapping[str, Any]]:
    """Return a normalized sequence of mapping items."""

    if not isinstance(value, list):
        return ()
    return [item for item in value if isinstance(item, Mapping)]


def _as_string_sequence(value: Any) -> list[str]:
    """Return a normalized list of non-empty strings."""

    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_target_columns(value: Any) -> list[dict[str, Any]]:
    """Return normalized contract target-column records."""

    if not isinstance(value, list):
        return []
    columns: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            columns.append({"name": item.strip()})
            continue
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        columns.append(
            {
                "name": name,
                "sensitivity": str(item.get("sensitivity") or "").strip() or None,
                "is_protected": bool(item.get("is_protected")),
                "protection_kind": (
                    str(item.get("protection_kind") or "").strip() or None
                ),
            }
        )
    return columns


def _update_annotation(
    annotations_by_target: dict[str, dict[str, Any]],
    *,
    target_name: str,
    target_kind: str,
    owner_name: str | None = None,
    owner_team: str | None = None,
    contract_name: str | None = None,
    contract_level: str | None = None,
    change_policy: str | None = None,
    sensitivity: str | None = None,
    is_protected: bool | None = None,
    protection_kind: str | None = None,
) -> None:
    """Merge one governance observation into the per-target overlay map."""

    annotation = annotations_by_target.setdefault(
        target_name,
        {
            "target_name": target_name,
            "target_kind": target_kind,
            "_owner_names": set(),
            "_owner_teams": set(),
            "_contract_names": set(),
            "_contract_levels": set(),
            "_change_policies": set(),
            "sensitivity": None,
            "is_protected": False,
            "protection_kind": None,
        },
    )
    if owner_name:
        annotation["_owner_names"].add(owner_name)
    if owner_team:
        annotation["_owner_teams"].add(owner_team)
    if contract_name:
        annotation["_contract_names"].add(contract_name)
    if contract_level:
        annotation["_contract_levels"].add(contract_level)
    if change_policy:
        annotation["_change_policies"].add(change_policy)
    if sensitivity:
        annotation["sensitivity"] = sensitivity
    if is_protected is not None:
        annotation["is_protected"] = bool(annotation["is_protected"] or is_protected)
    if protection_kind:
        annotation["protection_kind"] = protection_kind


def _finalize_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
    """Return one JSON-ready governance annotation row."""

    return {
        "target_name": annotation["target_name"],
        "target_kind": annotation["target_kind"],
        "owner_names": sorted(annotation["_owner_names"]),
        "owner_teams": sorted(annotation["_owner_teams"]),
        "contract_names": sorted(annotation["_contract_names"]),
        "contract_levels": sorted(annotation["_contract_levels"]),
        "change_policies": sorted(annotation["_change_policies"]),
        "sensitivity": annotation.get("sensitivity"),
        "is_protected": bool(annotation.get("is_protected")),
        "protection_kind": annotation.get("protection_kind"),
    }


__all__ = ["GovernanceReplayPlugin"]
