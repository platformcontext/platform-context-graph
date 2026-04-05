"""Focused deployment-overview mapping tests."""

from __future__ import annotations

from platform_context_graph.mcp.tools.handlers.ecosystem_support_overview import (
    build_deployment_overview,
)


def test_build_deployment_overview_surfaces_deployment_fact_summary() -> None:
    """Verify deployment overviews include fact summaries alongside facts."""

    overview = build_deployment_overview(
        hostnames=[
            {
                "hostname": "payments.stage.example.com",
                "visibility": "internal",
                "environment": "stage",
            }
        ],
        api_surface={},
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/shared:stage:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "stage",
                "name": "shared",
            }
        ],
        delivery_paths=[
            {
                "path_kind": "direct",
                "delivery_mode": "plain_kubernetes_manifests",
                "deployment_sources": ["service-manifests"],
                "config_sources": ["env-overlays"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/shared:stage:none"],
                "environments": ["stage"],
            }
        ],
    )

    assert overview["deployment_fact_summary"] == {
        "adapter": "evidence_only",
        "mapping_mode": "evidence_only",
        "overall_confidence": "medium",
        "evidence_sources": ["delivery_path", "platform", "entrypoint"],
        "high_confidence_fact_types": ["RUNS_ON_PLATFORM"],
        "medium_confidence_fact_types": [
            "DELIVERY_PATH_PRESENT",
            "USES_PACKAGING_LAYER",
            "DEPLOYS_FROM",
            "DISCOVERS_CONFIG_IN",
            "OBSERVED_IN_ENVIRONMENT",
            "EXPOSES_ENTRYPOINT",
        ],
        "limitations": ["deployment_controller_unknown"],
    }
