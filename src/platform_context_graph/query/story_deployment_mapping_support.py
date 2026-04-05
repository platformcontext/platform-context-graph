"""Support helpers for evidence-based deployment mapping."""

from __future__ import annotations

from typing import Any


def unique_strings(values: list[Any]) -> list[str]:
    """Return non-empty string values while preserving first-seen order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        rendered = value.strip()
        if not rendered or rendered in seen:
            continue
        seen.add(rendered)
        normalized.append(rendered)
    return normalized


def is_iac_adapter(adapter: str) -> bool:
    """Return whether the adapter represents infrastructure-as-code provisioning."""

    return adapter in {"cloudformation", "terraform"}


def delivery_rows(delivery_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return normalized delivery-path rows."""

    return [row for row in delivery_paths if isinstance(row, dict)]


def controller_rows(
    controller_driven_paths: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return controller-driven rows with usable controller kinds."""

    return [
        row
        for row in controller_driven_paths
        if isinstance(row, dict) and str(row.get("controller_kind") or "").strip()
    ]


def delivery_evidence(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build one normalized delivery-path evidence item."""

    if not isinstance(row, dict):
        return None
    evidence: dict[str, Any] = {"source": "delivery_path"}
    controller = str(row.get("controller") or "").strip()
    delivery_mode = str(row.get("delivery_mode") or "").strip()
    path_kind = str(row.get("path_kind") or "").strip()
    if controller:
        evidence["controller"] = controller
    if delivery_mode:
        evidence["delivery_mode"] = delivery_mode
    if not controller and path_kind:
        evidence["path_kind"] = path_kind
    return evidence


def controller_evidence(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build one normalized controller-driven evidence item."""

    if not isinstance(row, dict):
        return None
    return {
        "source": "controller_driven_path",
        "controller_kind": row.get("controller_kind"),
        "automation_kind": row.get("automation_kind"),
    }


def resolve_mapping_mode(
    *,
    delivery_rows: list[dict[str, Any]],
    controller_rows: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    observed_config_environments: list[str],
) -> tuple[str, str]:
    """Resolve the adapter and mapping mode from evidence-backed inputs."""

    if controller_rows:
        adapter = str(controller_rows[0].get("controller_kind") or "").strip()
        if adapter:
            return adapter, "iac" if is_iac_adapter(adapter) else "controller"

    for row in delivery_rows:
        adapter = str(row.get("controller") or "").strip()
        if adapter:
            return adapter, "iac" if is_iac_adapter(adapter) else "controller"

    if any([delivery_rows, platforms, entrypoints, observed_config_environments]):
        return "evidence_only", "evidence_only"
    return "", ""


def infer_packaging_kind(*, adapter: str, delivery_mode: str) -> str:
    """Infer the packaging layer from adapter-specific delivery modes."""

    if adapter == "terraform":
        if "helm" in delivery_mode:
            return "helm"
        if "kubernetes" in delivery_mode:
            return "kubernetes"
    if delivery_mode.startswith("flux_"):
        if "helmrelease" in delivery_mode:
            return "helm"
        if "kustomization" in delivery_mode:
            return "kustomize"
    return ""


def mapping_confidence(
    *,
    mapping_mode: str,
    controller_evidence: dict[str, Any] | None,
    inferred_packaging_kind: str,
) -> str:
    """Return the base confidence for one mapping mode."""

    if mapping_mode == "iac":
        return "high"
    if mapping_mode == "controller":
        return (
            "high"
            if controller_evidence is not None or inferred_packaging_kind
            else "medium"
        )
    if mapping_mode == "evidence_only":
        return "medium"
    return "low"
