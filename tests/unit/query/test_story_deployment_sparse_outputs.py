"""Sparse deployment-story output tests based on live validation patterns."""

from __future__ import annotations

from platform_context_graph.query.story import build_workload_story_response


def test_workload_story_surfaces_missing_deployment_evidence_summary() -> None:
    """Verify sparse service contexts expose a truthful deployment summary."""

    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:api-node-boats",
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "instance": None,
            "instances": [
                {
                    "id": "workload-instance:api-node-boats:default",
                    "type": "workload_instance",
                    "kind": "service",
                    "name": "api-node-boats",
                    "environment": "default",
                    "workload_id": "workload:api-node-boats",
                }
            ],
            "repositories": [
                {
                    "id": "repository:r_cd0afdc8",
                    "type": "repository",
                    "name": "api-node-boats",
                    "has_remote": False,
                }
            ],
            "dependencies": [
                {
                    "id": "workload:api-node-forex",
                    "type": "workload",
                    "kind": "service",
                    "name": "api-node-forex",
                }
            ],
            "entrypoints": [],
            "delivery_paths": [],
            "controller_driven_paths": [],
            "platforms": [],
            "observed_config_environments": [],
            "limitations": [
                "graph_partial",
                "content_partial",
                "runtime_platform_unknown",
                "deployment_chain_incomplete",
                "dns_unknown",
            ],
            "requested_as": "service",
        }
    )

    assert result["deployment_fact_summary"] == {
        "adapter": "unknown",
        "mapping_mode": "none",
        "overall_confidence": "low",
        "overall_confidence_reason": "no_deployment_evidence",
        "evidence_sources": [],
        "high_confidence_fact_types": [],
        "medium_confidence_fact_types": [],
        "fact_thresholds": {},
        "limitations": [
            "deployment_evidence_missing",
            "deployment_source_unknown",
            "runtime_platform_unknown",
            "environment_unknown",
            "entrypoint_unknown",
        ],
    }
