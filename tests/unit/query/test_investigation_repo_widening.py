"""Unit tests for related-repository widening during investigations."""

from __future__ import annotations

from platform_context_graph.query.investigation_repo_widening import (
    widen_related_repositories,
)


def test_widening_adds_repo_when_appset_references_external_source_repo() -> None:
    """Promote deployment source repositories discovered from ApplicationSets."""

    candidates = widen_related_repositories(
        service_name="api-node-boats",
        primary_repo_name="api-node-boats",
        deployment_trace={
            "argocd_applicationsets": [
                {
                    "source_repos": ["https://github.com/boatsgroup/helm-charts"],
                }
            ]
        },
    )

    assert candidates == [
        {
            "repo_id": None,
            "repo_name": "helm-charts",
            "reason": "argocd_source_repo",
            "evidence_families": ["deployment_controller", "gitops_config"],
        }
    ]


def test_widening_adds_repo_when_oidc_subject_mentions_service_repo() -> None:
    """Promote Terraform stack repos when GitHub OIDC role subjects match the service."""

    candidates = widen_related_repositories(
        service_name="api-node-boats",
        primary_repo_name="api-node-boats",
        repository_findings=[
            {
                "repo_name": "terraform-stack-node10",
                "oidc_subjects": [
                    "repo:boatsgroup/api-node-boats:ref:refs/heads/main",
                ],
            }
        ],
    )

    assert candidates == [
        {
            "repo_id": None,
            "repo_name": "terraform-stack-node10",
            "reason": "oidc_role_subject",
            "evidence_families": ["iac_infrastructure", "identity_and_iam"],
        }
    ]


def test_widening_adds_repo_when_workflow_mentions_external_deploy_repo() -> None:
    """Promote external deployment repos mentioned by app-repo workflow evidence."""

    candidates = widen_related_repositories(
        service_name="api-node-boats",
        primary_repo_name="api-node-boats",
        workflow_findings=[
            {
                "relative_path": ".github/workflows/release.yaml",
                "external_repositories": ["boatsgroup/helm-charts"],
            }
        ],
    )

    assert candidates == [
        {
            "repo_id": None,
            "repo_name": "helm-charts",
            "reason": "workflow_external_repo",
            "evidence_families": ["ci_cd_pipeline", "gitops_config"],
        }
    ]
