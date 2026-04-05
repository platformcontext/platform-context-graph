from __future__ import annotations

from platform_context_graph.query.story import (
    build_repository_story_response,
    build_workload_story_response,
)


def test_repository_story_subject_omits_server_local_checkout_paths() -> None:
    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_ab12cd34",
                "name": "payments-api",
                "repo_slug": "platformcontext/payments-api",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "local_path": "/srv/repos/payments-api",
                "path": "/srv/repos/payments-api",
                "has_remote": True,
            },
            "code": {"functions": 12, "classes": 3, "class_methods": 8},
        }
    )

    assert result["subject"] == {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-api",
        "repo_slug": "platformcontext/payments-api",
        "remote_url": "https://github.com/platformcontext/payments-api",
        "has_remote": True,
    }


def test_workload_story_omits_server_local_repo_paths_from_nested_items() -> None:
    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            },
            "repositories": [
                {
                    "id": "repository:r_ab12cd34",
                    "type": "repository",
                    "name": "payments-api",
                    "path": "/srv/repos/payments-api",
                    "local_path": "/srv/repos/payments-api",
                    "repo_slug": "platformcontext/payments-api",
                    "remote_url": "https://github.com/platformcontext/payments-api",
                    "has_remote": True,
                }
            ],
        }
    )

    repository = result["deployment_overview"]["repositories"][0]
    assert repository == {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-api",
        "repo_slug": "platformcontext/payments-api",
        "remote_url": "https://github.com/platformcontext/payments-api",
        "has_remote": True,
    }


def test_repository_story_exposes_richer_nested_context_without_server_paths() -> None:
    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_ab12cd34",
                "name": "payments-api",
                "repo_slug": "platformcontext/payments-api",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "local_path": "/srv/repos/payments-api",
                "path": "/srv/repos/payments-api",
                "has_remote": True,
            },
            "code": {"functions": 12, "classes": 3, "class_methods": 8},
            "hostnames": [
                {
                    "hostname": "payments-api.qa.example.com",
                    "environment": "qa",
                    "source_repo": "payments-api",
                    "relative_path": "config/qa.json",
                    "visibility": "public",
                }
            ],
            "api_surface": {
                "spec_files": [
                    {
                        "relative_path": "specs/index.yaml",
                        "discovered_from": "server/init/plugins/spec.js",
                    }
                ],
                "docs_routes": ["/_specs"],
                "api_versions": ["v3"],
                "endpoint_count": 1,
                "endpoints": [
                    {
                        "path": "/health",
                        "methods": ["get"],
                        "operation_ids": ["getHealth"],
                        "relative_path": "specs/paths/health.yaml",
                    }
                ],
            },
            "observed_config_environments": ["qa"],
            "delivery_workflows": {
                "github_actions": {
                    "commands": [
                        {
                            "command": "deploy",
                            "workflow": "deploy.yml",
                            "delivery_mode": "continuous_deployment",
                        }
                    ]
                }
            },
            "delivery_paths": [
                {
                    "path_kind": "direct",
                    "controller": "github_actions",
                    "delivery_mode": "continuous_deployment",
                    "deployment_sources": ["payments-api"],
                    "platform_kinds": ["ecs"],
                }
            ],
            "deployment_artifacts": {"config_paths": [{"path": "/configd/payments/*"}]},
            "consumer_repositories": [
                {
                    "repository": "payments-dashboard",
                    "evidence_kinds": ["hostname_reference"],
                    "sample_paths": ["group_vars/qa/app.yml"],
                }
            ],
            "deploys_from": [{"name": "helm-charts"}],
            "provisioned_by": [{"name": "terraform-stack"}],
            "iac_relationships": [{"type": "RUNS_IMAGE"}],
            "deployment_chain": [{"relationship_type": "DEPLOYS_FROM"}],
            "environments": ["qa"],
            "relationships": [{"type": "SELECTS"}],
            "ecosystem": {"dependencies": [{"name": "shared-lib"}]},
            "coverage": {
                "completeness_state": "complete",
                "repo_path": "/srv/repos/payments-api",
                "updated_at": "2026-03-27T00:00:00Z",
            },
            "limitations": [],
        }
    )

    overview = result["deployment_overview"]
    assert overview["api_surface"]["endpoints"][0]["path"] == "/health"
    assert overview["hostnames"][0]["hostname"] == "payments-api.qa.example.com"
    assert overview["observed_config_environments"] == ["qa"]
    assert (
        overview["delivery_workflows"]["github_actions"]["commands"][0]["command"]
        == "deploy"
    )
    assert overview["deploys_from"][0]["name"] == "helm-charts"
    assert overview["coverage"]["completeness_state"] == "complete"
    assert "repo_path" not in overview["coverage"]


def test_repository_story_handles_mixed_dependency_shapes() -> None:
    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_f9600c28",
                "name": "api-node-boats",
                "repo_slug": "boatsgroup/api-node-boats",
                "remote_url": "https://github.com/boatsgroup/api-node-boats",
                "has_remote": True,
                "file_count": 42,
            },
            "code": {"functions": 10, "classes": 2, "class_methods": 4},
            "deploys_from": [{"name": "helm-charts"}],
            "consumer_repositories": [],
            "ecosystem": {
                "dependencies": ["helm-charts", {"name": "shared-lib"}, {}],
            },
            "limitations": [],
        }
    )

    dependency_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "dependencies"
    )

    assert dependency_section["summary"] == (
        "Deploys from helm-charts and depends on helm-charts, shared-lib."
    )
    assert dependency_section["items"][-2:] == [
        {"type": "repository", "name": "helm-charts"},
        {"type": "repository", "name": "shared-lib"},
    ]


def test_workload_story_exposes_graph_evidence_in_deployment_overview() -> None:
    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:payments-api",
                "type": "workload",
                "kind": "service",
                "name": "payments-api",
            },
            "repositories": [
                {
                    "id": "repository:r_ab12cd34",
                    "type": "repository",
                    "name": "payments-api",
                    "repo_slug": "platformcontext/payments-api",
                    "remote_url": "https://github.com/platformcontext/payments-api",
                    "has_remote": True,
                }
            ],
            "cloud_resources": [
                {
                    "id": "cloud-resource:shared-payments-prod",
                    "type": "cloud_resource",
                    "name": "shared-payments-prod",
                }
            ],
            "evidence": [
                {
                    "source": "USES",
                    "detail": "cloud-resource:shared-payments-prod",
                    "weight": 1.0,
                }
            ],
            "requested_as": "service",
        }
    )

    assert result["deployment_overview"]["evidence"] == result["evidence"]
    assert result["deployment_overview"]["requested_as"] == "service"


def test_workload_story_mentions_entrypoints_and_repository_dependencies() -> None:
    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:api-node-boats",
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "instances": [
                {
                    "id": "workload-instance:api-node-boats:bg-qa",
                    "type": "workload_instance",
                    "kind": "service",
                    "name": "api-node-boats",
                    "environment": "bg-qa",
                    "workload_id": "workload:api-node-boats",
                }
            ],
            "dependencies": [
                {
                    "id": "repository:r_66cd2d76",
                    "type": "repository",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                    "remote_url": "https://github.com/boatsgroup/helm-charts",
                    "has_remote": True,
                }
            ],
            "entrypoints": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "qa",
                    "relative_path": "config/qa.json",
                    "visibility": "public",
                }
            ],
        }
    )

    assert "Public entrypoints: api-node-boats.qa.bgrp.io." in result["story"]
    assert "Depends on helm-charts." in result["story"]
    assert result["story_sections"][0]["id"] == "runtime"
    assert result["story_sections"][1]["id"] == "internet"
    assert result["story_sections"][2]["id"] == "dependencies"


def test_workload_story_uses_neutral_entrypoint_wording_for_internal_only_paths() -> (
    None
):
    """Internal-only docs and endpoints should not be labeled as public."""

    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:api-node-boats",
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "instances": [],
            "entrypoints": [],
            "api_surface": {
                "docs_routes": ["/_specs"],
                "endpoints": [{"path": "/_status"}],
            },
        }
    )

    assert "Public entrypoints" not in " ".join(result["story"])
    assert "Known entrypoints: /_status, /_specs." in result["story"]
    assert result["story_sections"][0]["summary"] == (
        "Known entrypoints include /_status, /_specs."
    )


def test_workload_story_exposes_generic_controller_and_runtime_overviews() -> None:
    """Verify workload stories expose controller/runtime evidence generically."""

    result = build_workload_story_response(
        {
            "workload": {
                "id": "workload:api-node-boats",
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "instance": {
                "id": "workload-instance:api-node-boats:bg-qa",
                "type": "workload_instance",
                "kind": "service",
                "name": "api-node-boats",
                "environment": "bg-qa",
                "workload_id": "workload:api-node-boats",
            },
            "repositories": [
                {
                    "id": "repository:r_f9600c28",
                    "type": "repository",
                    "name": "api-node-boats",
                    "repo_slug": "boatsgroup/api-node-boats",
                    "remote_url": "https://github.com/boatsgroup/api-node-boats",
                    "has_remote": True,
                }
            ],
            "entrypoints": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                    "relative_path": "config/qa.json",
                    "visibility": "public",
                }
            ],
            "platforms": [
                {
                    "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                    "kind": "eks",
                    "provider": "aws",
                    "environment": "bg-qa",
                    "name": "bg-qa",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                    "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
                    "environments": ["bg-qa"],
                    "summary": (
                        "ArgoCD drives a GitOps deployment path through "
                        "helm-charts onto EKS platforms."
                    ),
                }
            ],
            "controller_driven_paths": [
                {
                    "controller_kind": "argocd",
                    "automation_kind": "helm",
                    "entry_points": [
                        "argocd/api-node-boats/overlays/bg-qa/config.yaml"
                    ],
                    "target_descriptors": ["bg-qa", "api-node"],
                    "runtime_family": "kubernetes",
                    "supporting_repositories": ["helm-charts"],
                    "confidence": "high",
                    "explanation": (
                        "argocd controller config.yaml drives a helm deployment "
                        "into bg-qa."
                    ),
                }
            ],
            "observed_config_environments": ["bg-qa"],
        }
    )

    assert result["controller_overview"] == {
        "families": ["argocd"],
        "delivery_modes": ["eks_gitops"],
        "controllers": [
            {
                "family": "argocd",
                "path_kinds": ["gitops"],
                "delivery_modes": ["eks_gitops"],
                "automation_kinds": ["helm"],
                "entry_points": ["argocd/api-node-boats/overlays/bg-qa/config.yaml"],
                "target_descriptors": ["bg-qa", "api-node"],
                "supporting_repositories": ["helm-charts"],
                "confidence": "high",
            }
        ],
    }
    assert result["runtime_overview"] == {
        "selected_environment": "bg-qa",
        "observed_environments": ["bg-qa"],
        "platform_kinds": ["eks"],
        "platforms": [
            {
                "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                "kind": "eks",
                "provider": "aws",
                "environment": "bg-qa",
                "name": "bg-qa",
            }
        ],
        "entrypoints": ["api-node-boats.qa.bgrp.io"],
    }
    assert result["deployment_facts"] == [
        {
            "fact_type": "MANAGED_BY_CONTROLLER",
            "adapter": "argocd",
            "value": "argocd",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                },
                {
                    "source": "controller_driven_path",
                    "controller_kind": "argocd",
                    "automation_kind": "helm",
                },
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "argocd",
            "value": "helm",
            "confidence": "high",
            "evidence": [
                {
                    "source": "controller_driven_path",
                    "controller_kind": "argocd",
                    "automation_kind": "helm",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "argocd",
            "value": "helm-charts",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "argocd",
            "value": "eks",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "eks",
                    "environment": "bg-qa",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "argocd",
            "value": "bg-qa",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                }
            ],
        },
        {
            "fact_type": "EXPOSES_ENTRYPOINT",
            "adapter": "argocd",
            "value": "api-node-boats.qa.bgrp.io",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "entrypoint",
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                }
            ],
        },
    ]


def test_repository_story_exposes_generic_controller_and_runtime_overviews() -> None:
    """Verify repository stories expose generic controller/runtime overviews."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_f9600c28",
                "name": "api-node-boats",
                "repo_slug": "boatsgroup/api-node-boats",
                "remote_url": "https://github.com/boatsgroup/api-node-boats",
                "has_remote": True,
            },
            "code": {"functions": 10, "classes": 2, "class_methods": 4},
            "hostnames": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                    "visibility": "public",
                }
            ],
            "platforms": [
                {
                    "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                    "kind": "eks",
                    "provider": "aws",
                    "environment": "bg-qa",
                    "name": "bg-qa",
                }
            ],
            "observed_config_environments": ["bg-qa"],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                    "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
                    "environments": ["bg-qa"],
                    "summary": (
                        "ArgoCD drives a GitOps deployment path through "
                        "helm-charts onto EKS platforms."
                    ),
                }
            ],
            "controller_driven_paths": [
                {
                    "controller_kind": "argocd",
                    "automation_kind": "helm",
                    "entry_points": [
                        "argocd/api-node-boats/overlays/bg-qa/config.yaml"
                    ],
                    "target_descriptors": ["bg-qa", "api-node"],
                    "runtime_family": "kubernetes",
                    "supporting_repositories": ["helm-charts"],
                    "confidence": "high",
                }
            ],
            "limitations": [],
        }
    )

    assert result["controller_overview"]["families"] == ["argocd"]
    assert result["controller_overview"]["delivery_modes"] == ["eks_gitops"]
    assert result["runtime_overview"] == {
        "selected_environment": "bg-qa",
        "observed_environments": ["bg-qa"],
        "platform_kinds": ["eks"],
        "platforms": [
            {
                "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                "kind": "eks",
                "provider": "aws",
                "environment": "bg-qa",
                "name": "bg-qa",
            }
        ],
        "entrypoints": ["api-node-boats.qa.bgrp.io"],
    }
