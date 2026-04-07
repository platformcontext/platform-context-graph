"""Investigation-specific OpenAPI examples."""

from __future__ import annotations

INVESTIGATION_RESPONSE_EXAMPLE = {
    "summary": [
        "Investigation intent: deployment.",
        "Primary service: api-node-boats.",
    ],
    "repositories_considered": [
        {
            "repo_id": "repository:r_app12345",
            "repo_name": "api-node-boats",
            "reason": "primary_service_repository",
            "evidence_families": ["service_runtime"],
        },
        {
            "repo_id": "repository:r_tf12345",
            "repo_name": "terraform-stack-node10",
            "reason": "oidc_role_subject",
            "evidence_families": ["iac_infrastructure", "identity_and_iam"],
        },
    ],
    "repositories_with_evidence": [
        {
            "repo_id": "repository:r_tf12345",
            "repo_name": "terraform-stack-node10",
            "reason": "oidc_role_subject",
            "evidence_families": ["iac_infrastructure", "identity_and_iam"],
        }
    ],
    "evidence_families_found": [
        "service_runtime",
        "deployment_controller",
        "gitops_config",
        "iac_infrastructure",
        "identity_and_iam",
        "ci_cd_pipeline",
    ],
    "coverage_summary": {
        "searched_repository_count": 3,
        "repositories_with_evidence_count": 1,
        "searched_evidence_families": [
            "service_runtime",
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
            "identity_and_iam",
            "ci_cd_pipeline",
        ],
        "found_evidence_families": [
            "service_runtime",
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
            "identity_and_iam",
            "ci_cd_pipeline",
        ],
        "missing_evidence_families": [],
        "deployment_mode": "multi_plane",
        "deployment_planes": [
            {
                "name": "gitops_controller_plane",
                "evidence_families": ["deployment_controller", "gitops_config"],
            },
            {
                "name": "iac_infrastructure_plane",
                "evidence_families": ["iac_infrastructure"],
            },
        ],
        "graph_completeness": "partial",
        "content_completeness": "partial",
    },
    "investigation_findings": [
        {
            "title": "Service investigation initialized",
            "summary": (
                "PCG combined service, deployment, workflow, and related "
                "repository evidence for this service."
            ),
            "evidence_families": [
                "service_runtime",
                "deployment_controller",
                "gitops_config",
                "iac_infrastructure",
                "identity_and_iam",
                "ci_cd_pipeline",
            ],
        }
    ],
    "limitations": ["runtime_instance_missing"],
    "recommended_next_steps": [
        "Inspect the highest-signal related deployment repository next."
    ],
    "recommended_next_calls": [
        {
            "tool": "get_repo_story",
            "reason": "related_deployment_repository",
            "args": {"repo_id": "repository:r_tf12345"},
        }
    ],
}
