"""Shared evidence-family definitions for investigation orchestration."""

from __future__ import annotations

INVESTIGATION_EVIDENCE_FAMILIES = (
    "service_runtime",
    "deployment_controller",
    "gitops_config",
    "iac_infrastructure",
    "network_routing",
    "identity_and_iam",
    "dependencies",
    "support_artifacts",
    "monitoring_observability",
    "ci_cd_pipeline",
)

__all__ = ["INVESTIGATION_EVIDENCE_FAMILIES"]
