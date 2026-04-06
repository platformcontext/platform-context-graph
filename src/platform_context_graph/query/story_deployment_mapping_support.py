"""Support helpers for evidence-based deployment mapping."""

from __future__ import annotations

from typing import Any

PACKAGING_AUTOMATION_KINDS = frozenset({"helm", "kubernetes", "kustomize"})
FACT_THRESHOLD_CODES = {
    "PROVISIONED_BY_IAC": "explicit_iac_adapter",
    "MANAGED_BY_CONTROLLER": "explicit_controller_signal",
    "USES_PACKAGING_LAYER": "explicit_packaging_signal",
    "USES_AUTOMATION_LAYER": "explicit_automation_signal",
    "DEPLOYS_FROM": "named_deployment_source",
    "DISCOVERS_CONFIG_IN": "named_config_source",
    "RUNS_ON_PLATFORM": "explicit_platform_match",
    "OBSERVED_IN_ENVIRONMENT": "explicit_environment_evidence",
    "EXPOSES_ENTRYPOINT": "named_entrypoint",
    "DELIVERY_PATH_PRESENT": "delivery_path_present",
}


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


def infer_packaging_kind(
    *,
    adapter: str,
    delivery_mode: str,
    platform_kinds: list[str],
) -> str:
    """Infer the packaging layer from adapter-specific delivery and runtime evidence."""

    normalized_platform_kinds = {
        kind.strip().lower() for kind in platform_kinds if kind.strip()
    }
    if adapter == "terraform":
        if "helm" in delivery_mode:
            return "helm"
        if "kubernetes" in delivery_mode:
            return "kubernetes"
    if adapter == "cloudformation" and "serverless" in delivery_mode:
        return "serverless"
    if adapter == "evidence_only":
        if "helm" in delivery_mode:
            return "helm"
        if "kustom" in delivery_mode:
            return "kustomize"
        if "kubernetes" in delivery_mode or "manifest" in delivery_mode:
            return "kubernetes"
    if delivery_mode.startswith("flux_"):
        if "helmrelease" in delivery_mode:
            return "helm"
        if "kustomization" in delivery_mode:
            return "kustomize"
    if "ecs" in normalized_platform_kinds:
        if adapter == "codedeploy":
            return "container"
        if delivery_mode in {"continuous_deployment", "ecs_service_deployment"}:
            return "container"
    return ""


def normalize_controller_packaging_kind(automation_kind: str) -> str:
    """Return a packaging kind only for controller automation that packages artifacts."""

    normalized = automation_kind.strip().lower()
    if normalized in PACKAGING_AUTOMATION_KINDS:
        return normalized
    return ""


def normalize_automation_layer(automation_kind: str) -> str:
    """Return a controller automation layer that is not a packaging primitive."""

    normalized = automation_kind.strip().lower()
    if not normalized or normalized in PACKAGING_AUTOMATION_KINDS:
        return ""
    return normalized


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


def overall_confidence_reason(
    *,
    mapping_mode: str,
    controller_evidence: dict[str, Any] | None,
    inferred_packaging_kind: str,
) -> str:
    """Return the top-level reason code for the selected confidence."""

    if mapping_mode == "iac":
        return "explicit_iac_adapter"
    if mapping_mode == "controller":
        if controller_evidence is not None:
            return "explicit_controller_signal"
        if inferred_packaging_kind:
            return "explicit_packaging_signal"
        return "controller_delivery_signal"
    if mapping_mode == "evidence_only":
        return "delivery_runtime_evidence_without_named_adapter"
    return "confidence_unknown"


def build_mapping_limitations(
    *,
    mapping_mode: str,
    has_deploy_source: bool,
    has_config_source: bool,
    has_platform: bool,
    has_environment: bool,
    has_entrypoint: bool,
    saw_delivery_rows: bool,
) -> list[str]:
    """Return standardized deployment-mapping limitation codes."""

    limitations: list[str] = []
    if mapping_mode == "evidence_only":
        limitations.append("deployment_controller_unknown")
    if not has_deploy_source:
        limitations.append("deployment_source_unknown")
    if saw_delivery_rows and not has_config_source:
        limitations.append("config_source_unknown")
    if not has_platform:
        limitations.append("runtime_platform_unknown")
    if not has_environment:
        limitations.append("environment_unknown")
    if not has_entrypoint:
        limitations.append("entrypoint_unknown")
    return limitations


def fact_threshold_code(fact_type: str) -> str:
    """Return the threshold code for one normalized deployment fact type."""

    return FACT_THRESHOLD_CODES.get(fact_type, "threshold_unknown")
