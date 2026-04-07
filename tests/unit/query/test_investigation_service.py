"""Unit tests for investigation coverage and deployment-plane reporting."""

from __future__ import annotations

from platform_context_graph.query.investigation_recommendations import (
    build_recommended_next_calls,
)
from platform_context_graph.query.investigation_service import (
    _add_related_repo_details,
)
from platform_context_graph.query.investigation_service import investigate_service
from platform_context_graph.query.investigation_coverage import (
    build_investigation_coverage_summary,
)


def test_build_coverage_summary_marks_multi_plane_when_controller_and_iac_exist() -> (
    None
):
    """Report multiple planes when controller and IAC evidence coexist."""

    summary = build_investigation_coverage_summary(
        repositories_considered_count=4,
        repositories_with_evidence_count=3,
        searched_evidence_families=[
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
            "network_routing",
        ],
        found_evidence_families=[
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
        ],
        graph_completeness="partial",
        content_completeness="partial",
    )

    assert summary.deployment_mode == "multi_plane"
    assert [plane.name for plane in summary.deployment_planes] == [
        "gitops_controller_plane",
        "iac_infrastructure_plane",
    ]
    assert summary.missing_evidence_families == ["network_routing"]


def test_build_coverage_summary_marks_single_plane_when_only_gitops_exists() -> None:
    """Keep single-plane classification when only controller-backed evidence exists."""

    summary = build_investigation_coverage_summary(
        repositories_considered_count=2,
        repositories_with_evidence_count=2,
        searched_evidence_families=["deployment_controller", "gitops_config"],
        found_evidence_families=["deployment_controller", "gitops_config"],
        graph_completeness="complete",
        content_completeness="partial",
    )

    assert summary.deployment_mode == "single_plane"
    assert [plane.name for plane in summary.deployment_planes] == [
        "gitops_controller_plane"
    ]


def test_build_coverage_summary_marks_sparse_when_only_runtime_exists() -> None:
    """Report sparse mode when deployment evidence is missing but runtime exists."""

    summary = build_investigation_coverage_summary(
        repositories_considered_count=1,
        repositories_with_evidence_count=1,
        searched_evidence_families=["service_runtime", "network_routing"],
        found_evidence_families=["service_runtime"],
        graph_completeness="partial",
        content_completeness="unknown",
    )

    assert summary.deployment_mode == "sparse"
    assert summary.deployment_planes == []
    assert summary.missing_evidence_families == ["network_routing"]


def test_investigate_service_surfaces_dual_deployment_planes(
    monkeypatch,
) -> None:
    """Preserve separate GitOps and Terraform planes in one investigation."""

    def fake_resolve_entity(_database, **_kwargs):
        return {
            "matches": [
                {
                    "ref": {
                        "id": "workload:api-node-boats",
                        "type": "workload",
                        "kind": "service",
                        "name": "api-node-boats",
                    },
                    "score": 0.99,
                },
                {
                    "ref": {
                        "id": "repository:r_app12345",
                        "type": "repository",
                        "name": "api-node-boats",
                    },
                    "score": 0.97,
                },
            ]
        }

    def fake_get_service_story(_database, **_kwargs):
        return {
            "subject": {
                "id": "workload:api-node-boats",
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "deployment_overview": {
                "internet_entrypoints": ["api-node-boats.qa.bgrp.io"],
            },
            "limitations": ["runtime_instance_missing"],
        }

    def fake_trace_deployment_chain(_database, service_name, **_kwargs):
        assert service_name == "api-node-boats"
        return {
            "argocd_applicationsets": [
                {"source_repos": ["https://github.com/boatsgroup/helm-charts"]}
            ]
        }

    def fake_get_repository_story(_database, **kwargs):
        repo_id = kwargs["repo_id"]
        if repo_id == "repository:r_app12345":
            return {
                "subject": {
                    "id": repo_id,
                    "type": "repository",
                    "name": "api-node-boats",
                },
                "story": ["Runtime service repo."],
            }
        return {
            "subject": {
                "id": "repository:r_tf12345",
                "type": "repository",
                "name": "terraform-stack-node10",
            },
            "story": ["Terraform deployment stack."],
        }

    def fake_get_repository_context(_database, **kwargs):
        repo_id = kwargs["repo_id"]
        if repo_id == "repository:r_app12345":
            return {
                "repository": {
                    "id": repo_id,
                    "name": "api-node-boats",
                }
            }
        return {
            "repository": {
                "id": "repository:r_tf12345",
                "name": "terraform-stack-node10",
            }
        }

    def fake_search_file_content(_database, **kwargs):
        repo_ids = kwargs.get("repo_ids") or []
        if repo_ids == ["repository:r_app12345"]:
            return {
                "matches": [
                    {
                        "repo_id": "repository:r_app12345",
                        "relative_path": ".github/workflows/release.yaml",
                        "snippet": "boatsgroup/helm-charts",
                        "source_backend": "postgres",
                    }
                ]
            }
        return {"matches": []}

    def fake_add_related_repo_details(_database, *, widened_repositories):
        return [
            {
                "repo_id": "repository:r_tf12345",
                "repo_name": "terraform-stack-node10",
                "reason": "oidc_role_subject",
                "evidence_families": ["iac_infrastructure", "identity_and_iam"],
            },
            *widened_repositories,
        ]

    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.entity_resolution_queries.resolve_entity",
        fake_resolve_entity,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.context_queries.get_service_story",
        fake_get_service_story,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.trace_deployment_chain",
        fake_trace_deployment_chain,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.repository_queries.get_repository_story",
        fake_get_repository_story,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.repository_queries.get_repository_context",
        fake_get_repository_context,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.content_queries.search_file_content",
        fake_search_file_content,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service._add_related_repo_details",
        fake_add_related_repo_details,
    )

    result = investigate_service(
        database=object(),
        service_name="api-node-boats",
        intent="deployment",
    )

    assert result["coverage_summary"]["deployment_mode"] == "multi_plane"
    assert result["evidence_families_found"] == [
        "service_runtime",
        "deployment_controller",
        "gitops_config",
        "iac_infrastructure",
        "identity_and_iam",
        "ci_cd_pipeline",
    ]
    assert (
        result["repositories_with_evidence"][0]["repo_name"] == "terraform-stack-node10"
    )
    assert result["recommended_next_calls"] == [
        {
            "tool": "get_repo_story",
            "reason": "related_deployment_repository",
            "args": {"repo_id": "repository:r_tf12345"},
        }
    ]


def test_add_related_repo_details_resolves_canonical_repository_ids(
    monkeypatch,
) -> None:
    """Resolve widened repository names to canonical repository identifiers."""

    def fake_resolve_entity(_database, **kwargs):
        if kwargs["query"] == "terraform-stack-node10":
            return {
                "matches": [
                    {
                        "ref": {
                            "id": "repository:r_tf12345",
                            "type": "repository",
                            "name": "terraform-stack-node10",
                        }
                    }
                ]
            }
        return {"matches": []}

    monkeypatch.setattr(
        "platform_context_graph.query.investigation_service.entity_resolution_queries.resolve_entity",
        fake_resolve_entity,
    )

    detailed = _add_related_repo_details(
        object(),
        widened_repositories=[
            {
                "repo_name": "terraform-stack-node10",
                "reason": "oidc_role_subject",
                "evidence_families": ["iac_infrastructure"],
            },
            {
                "repo_name": "unknown-repo",
                "reason": "workflow_reference",
                "evidence_families": ["ci_cd_pipeline"],
            },
        ],
    )

    assert detailed == [
        {
            "repo_id": "repository:r_tf12345",
            "repo_name": "terraform-stack-node10",
            "reason": "oidc_role_subject",
            "evidence_families": ["iac_infrastructure"],
        },
        {
            "repo_name": "unknown-repo",
            "reason": "workflow_reference",
            "evidence_families": ["ci_cd_pipeline"],
        },
    ]


def test_build_recommended_next_calls_skips_primary_repository() -> None:
    """Do not recommend the primary repository as the next deployment repo."""

    result = build_recommended_next_calls(
        repositories_with_evidence=[
            {
                "repo_id": "repository:r_app12345",
                "repo_name": "payments-api",
                "reason": "primary_service_repository",
                "evidence_families": ["service_runtime"],
            },
            {
                "repo_id": "repository:r_tf12345",
                "repo_name": "terraform-stack-payments",
                "reason": "oidc_role_subject",
                "evidence_families": ["iac_infrastructure"],
            },
        ],
        primary_repo_name="payments-api",
    )

    assert [call.model_dump(mode="json") for call in result] == [
        {
            "tool": "get_repo_story",
            "reason": "related_deployment_repository",
            "args": {"repo_id": "repository:r_tf12345"},
        }
    ]
