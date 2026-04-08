"""Unit tests for investigation response models."""

from __future__ import annotations

from platform_context_graph.domain.investigation_responses import (
    InvestigationResponse,
)


def test_investigation_response_allows_typed_coverage_and_next_calls() -> None:
    """Preserve the top-level investigation contract shape."""

    payload = InvestigationResponse.model_validate(
        {
            "summary": ["dual deployment detected"],
            "framework_summary": {
                "frameworks": ["express", "nextjs", "react"],
                "express": {
                    "module_count": 1,
                    "route_path_count": 2,
                    "route_methods": ["GET", "POST"],
                    "sample_modules": [
                        {
                            "relative_path": "server/routes.js",
                            "route_methods": ["GET", "POST"],
                            "route_paths": ["/health", "/orders"],
                            "server_symbols": ["app"],
                        }
                    ],
                },
                "react": {
                    "module_count": 2,
                    "client_boundary_count": 1,
                    "server_boundary_count": 0,
                    "shared_boundary_count": 1,
                    "component_module_count": 2,
                    "hook_module_count": 1,
                    "sample_modules": [
                        {
                            "relative_path": "app/orders/page.tsx",
                            "boundary": "client",
                            "component_exports": ["default"],
                            "hooks_used": ["useState"],
                        }
                    ],
                },
                "nextjs": {
                    "module_count": 2,
                    "page_count": 1,
                    "layout_count": 1,
                    "route_count": 0,
                    "metadata_module_count": 1,
                    "route_handler_module_count": 0,
                    "client_runtime_count": 1,
                    "server_runtime_count": 1,
                    "route_verbs": [],
                    "sample_modules": [
                        {
                            "relative_path": "app/orders/page.tsx",
                            "module_kind": "page",
                            "route_verbs": [],
                            "metadata_exports": "dynamic",
                            "route_segments": ["orders"],
                            "runtime_boundary": "client",
                        }
                    ],
                },
            },
            "repositories_considered": [
                {
                    "repo_id": "repository:r_app12345",
                    "repo_name": "api-node-boats",
                    "reason": "primary_service_repository",
                    "evidence_families": ["service_runtime"],
                }
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
                "gitops_config",
                "iac_infrastructure",
            ],
            "coverage_summary": {
                "searched_repository_count": 3,
                "repositories_with_evidence_count": 2,
                "searched_evidence_families": [
                    "service_runtime",
                    "gitops_config",
                    "iac_infrastructure",
                ],
                "found_evidence_families": [
                    "service_runtime",
                    "gitops_config",
                    "iac_infrastructure",
                ],
                "missing_evidence_families": ["ci_cd_pipeline"],
                "deployment_mode": "multi_plane",
                "deployment_planes": [
                    {
                        "name": "gitops_kubernetes",
                        "evidence_families": ["gitops_config"],
                    },
                    {
                        "name": "terraform_ecs",
                        "evidence_families": ["iac_infrastructure"],
                    },
                ],
                "graph_completeness": "partial",
                "content_completeness": "partial",
            },
            "investigation_findings": [
                {
                    "title": "Dual deployment detected",
                    "summary": "GitOps and Terraform evidence both exist.",
                    "evidence_families": ["gitops_config", "iac_infrastructure"],
                }
            ],
            "limitations": ["runtime_instance_missing"],
            "recommended_next_steps": [
                "Inspect the Terraform stack for runtime details."
            ],
            "recommended_next_calls": [
                {
                    "tool": "get_repo_story",
                    "reason": "terraform_stack_detected",
                    "args": {"repo_id": "repository:r_tf12345"},
                }
            ],
        }
    )

    assert payload.coverage_summary.deployment_mode == "multi_plane"
    assert payload.framework_summary is not None
    assert payload.framework_summary.express is not None
    assert payload.framework_summary.express.route_path_count == 2
    assert payload.framework_summary.nextjs is not None
    assert payload.framework_summary.nextjs.page_count == 1
    assert payload.recommended_next_calls[0].tool == "get_repo_story"
