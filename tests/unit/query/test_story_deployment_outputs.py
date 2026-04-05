"""Story output tests for deployment fact summaries."""

from __future__ import annotations

from platform_context_graph.query.story import build_repository_story_response
from platform_context_graph.query.story import build_workload_story_response


def test_workload_story_surfaces_deployment_fact_summary_for_evidence_only_mode() -> (
    None
):
    """Verify workload stories expose evidence-only fact summaries."""

    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            },
            "delivery_paths": [
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
            "platforms": [
                {
                    "id": "platform:kubernetes:aws:cluster/shared:stage:none",
                    "kind": "kubernetes",
                    "provider": "aws",
                    "environment": "stage",
                    "name": "shared",
                }
            ],
            "entrypoints": [
                {
                    "hostname": "payments.stage.example.com",
                    "environment": "stage",
                    "visibility": "internal",
                }
            ],
            "observed_config_environments": ["stage"],
        }
    )

    assert result["deployment_fact_summary"] == {
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


def test_repository_story_surfaces_deployment_fact_summary_for_cloudformation() -> None:
    """Verify repository stories expose fact summaries for IAC-backed evidence."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_ab12cd34",
                "name": "payments-api",
                "repo_slug": "platformcontext/payments-api",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "has_remote": True,
            },
            "code": {"functions": 1, "classes": 0, "class_methods": 0},
            "hostnames": [
                {
                    "hostname": "payments.prod.example.com",
                    "environment": "prod",
                    "visibility": "public",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "direct",
                    "controller": "cloudformation",
                    "delivery_mode": "cloudformation_eks",
                    "deployment_sources": ["service-catalog"],
                    "config_sources": ["cluster-networking"],
                    "platform_kinds": ["eks"],
                    "platforms": ["platform:eks:aws:cluster/prod-1:prod:us-east-1"],
                    "environments": ["prod"],
                }
            ],
            "platforms": [
                {
                    "id": "platform:eks:aws:cluster/prod-1:prod:us-east-1",
                    "kind": "eks",
                    "provider": "aws",
                    "environment": "prod",
                    "name": "prod-1",
                }
            ],
            "observed_config_environments": ["prod"],
            "limitations": [],
        }
    )

    assert result["deployment_fact_summary"] == {
        "adapter": "cloudformation",
        "mapping_mode": "iac",
        "overall_confidence": "high",
        "evidence_sources": ["delivery_path", "platform", "entrypoint"],
        "high_confidence_fact_types": [
            "PROVISIONED_BY_IAC",
            "DEPLOYS_FROM",
            "DISCOVERS_CONFIG_IN",
            "RUNS_ON_PLATFORM",
            "OBSERVED_IN_ENVIRONMENT",
        ],
        "medium_confidence_fact_types": ["EXPOSES_ENTRYPOINT"],
        "limitations": [],
    }
