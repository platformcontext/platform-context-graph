"""Focused story overview tests for GitOps and documentation responses."""

from __future__ import annotations

from platform_context_graph.query.story import (
    build_repository_story_response,
    build_workload_story_response,
)


def test_repository_story_exposes_gitops_documentation_and_support_overviews() -> None:
    """Repository stories should expose the new overview sections."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "repo_slug": "boatsgroup/api-node-boats",
                "remote_url": "https://github.com/boatsgroup/api-node-boats",
                "has_remote": True,
            },
            "code": {"functions": 10, "classes": 2, "class_methods": 4},
            "hostnames": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "qa",
                    "source_repo": "helm-charts",
                    "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    "visibility": "public",
                }
            ],
            "api_surface": {
                "api_versions": ["v3"],
                "docs_routes": ["/_specs"],
                "endpoints": [
                    {"path": "/health", "relative_path": "specs/openapi.yaml"}
                ],
            },
            "deploys_from": [
                {
                    "id": "repository:r_helm_charts",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                }
            ],
            "discovers_config_in": [
                {
                    "id": "repository:r_iac",
                    "name": "iac-eks-pcg",
                    "repo_slug": "boatsgroup/iac-eks-pcg",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                    "summary": "GitHub Actions drives a GitOps deployment path through helm-charts onto EKS platforms.",
                }
            ],
            "deployment_artifacts": {
                "charts": [
                    {
                        "repository": "boatsgroup.pe.jfrog.io/bg-helm/api-node-template",
                        "version": "0.2.1",
                        "release_name": "api-node-boats",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                    }
                ],
                "images": [
                    {
                        "repository": "048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                        "tag": "3.21.0",
                        "source_repo": "helm-charts",
                    }
                ],
                "service_ports": [
                    {
                        "port": 3081,
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/values.yaml",
                    }
                ],
                "gateways": [
                    {
                        "name": "envoy-internal",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    }
                ],
                "kustomize_resources": [
                    {
                        "kind": "XIRSARole",
                        "name": "api-node-boats",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                    }
                ],
                "config_paths": [
                    {
                        "path": "argocd/api-node-boats/base/values.yaml",
                        "source_repo": "helm-charts",
                    },
                    {
                        "path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "source_repo": "helm-charts",
                    },
                ],
            },
            "observed_config_environments": ["bg-qa"],
            "environments": ["qa", "bg-qa"],
            "documentation_evidence": {
                "graph_context": [
                    {
                        "kind": "delivery_path",
                        "detail": "github_actions eks_gitops",
                    }
                ],
                "file_content": [
                    {
                        "repo_id": "repository:r_api_node_boats",
                        "relative_path": "README.md",
                        "source_backend": "postgres",
                        "title": "API Node Boats",
                        "summary": "Service overview and local debugging notes.",
                    }
                ],
                "entity_content": [],
                "content_search": [
                    {
                        "repo_id": "repository:r_helm_charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "source_backend": "postgres",
                        "snippet": "hostnames: api-node-boats.qa.bgrp.io",
                    }
                ],
            },
            "limitations": [],
        }
    )

    story_section_ids = [section["id"] for section in result["story_sections"]]
    assert story_section_ids[-3:] == ["gitops", "documentation", "support"]
    assert result["gitops_overview"]["owner"]["delivery_controllers"] == [
        "github_actions"
    ]
    assert result["gitops_overview"]["value_layers"][0]["relative_path"] == (
        "argocd/api-node-boats/base/values.yaml"
    )
    assert (
        result["documentation_overview"]["documentation_evidence"]["file_content"][0][
            "relative_path"
        ]
        == "README.md"
    )
    assert result["support_overview"]["investigation_paths"][0]["topic"] == (
        "request_failures"
    )
    assert result["support_overview"]["key_artifacts"][0]["relative_path"] == (
        "argocd/api-node-boats/overlays/bg-qa/values.yaml"
    )


def test_workload_story_exposes_gitops_documentation_and_support_overviews() -> None:
    """Workload stories should expose the new overview sections."""

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
                    "id": "repository:r_api_node_boats",
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
                    "visibility": "public",
                },
                {
                    "hostname": "api-node-boats.platformcontextgraph.svc.cluster.local",
                    "environment": "bg-qa",
                    "visibility": "internal",
                },
            ],
            "api_surface": {
                "docs_routes": ["/_specs"],
                "api_versions": ["v3"],
                "endpoints": [
                    {"path": "/_status", "relative_path": "catalog-specs.yaml"},
                    {"path": "/boats/search", "relative_path": "catalog-specs.yaml"},
                ],
            },
            "deploys_from": [
                {
                    "id": "repository:r_helm_charts",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
            "deployment_artifacts": {
                "charts": [
                    {
                        "repository": "boatsgroup.pe.jfrog.io/bg-helm/api-node-template",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                    }
                ],
                "config_paths": [
                    {
                        "path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "source_repo": "helm-charts",
                    }
                ],
                "service_ports": [
                    {
                        "port": 3081,
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/values.yaml",
                    }
                ],
                "gateways": [
                    {
                        "name": "envoy-internal",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    }
                ],
            },
            "documentation_evidence": {
                "graph_context": [
                    {"kind": "entrypoint", "detail": "api-node-boats.qa.bgrp.io"}
                ],
                "file_content": [
                    {
                        "repo_id": "repository:r_api_node_boats",
                        "relative_path": "README.md",
                        "source_backend": "postgres",
                        "title": "API Node Boats",
                        "summary": "Service overview and local debugging notes.",
                    }
                ],
                "entity_content": [],
                "content_search": [],
            },
            "requested_as": "service",
            "limitations": [],
        }
    )

    story_section_ids = [section["id"] for section in result["story_sections"]]
    assert story_section_ids[-4:] == [
        "deployment",
        "gitops",
        "documentation",
        "support",
    ]
    assert result["gitops_overview"]["environment"]["selected"] == "bg-qa"
    assert result["deployment_overview"]["internet_entrypoints"][0]["hostname"] == (
        "api-node-boats.qa.bgrp.io"
    )
    assert result["deployment_overview"]["api_surface"]["docs_routes"] == ["/_specs"]
    assert result["support_overview"]["entrypoints"][0]["hostname"] == (
        "api-node-boats.qa.bgrp.io"
    )


def test_repository_story_ranks_support_artifacts_ahead_of_generic_docs() -> None:
    """Support artifacts should outrank generic README-style documentation."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "repo_slug": "boatsgroup/api-node-boats",
                "remote_url": "https://github.com/boatsgroup/api-node-boats",
                "has_remote": True,
            },
            "code": {"functions": 10, "classes": 2, "class_methods": 4},
            "api_surface": {
                "spec_files": [
                    {
                        "relative_path": "specs/openapi.yaml",
                        "discovered_from": "api-node-boats.ts",
                    }
                ],
                "endpoints": [
                    {
                        "path": "/_status",
                        "relative_path": "catalog-specs.yaml",
                    }
                ],
            },
            "deploys_from": [
                {
                    "id": "repository:r_helm",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
            "deployment_artifacts": {
                "config_paths": [
                    {
                        "path": "argocd/api-node-boats/base/values.yaml",
                        "source_repo": "helm-charts",
                    },
                    {
                        "path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "source_repo": "helm-charts",
                    },
                ],
                "kustomize_resources": [
                    {
                        "kind": "XIRSARole",
                        "name": "api-node-boats",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                    },
                    {
                        "kind": "ConfigMap",
                        "name": "dashboard-overview",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/dashboards/dashboard-overview-configmap.yaml",
                    },
                ],
            },
            "documentation_evidence": {
                "graph_context": [],
                "file_content": [
                    {
                        "repo_id": "repository:r_api_node_boats",
                        "relative_path": "README.md",
                        "source_backend": "postgres",
                        "title": "API Node Boats",
                        "summary": "Repository overview and local debugging notes.",
                    },
                    {
                        "repo_id": "repository:r_api_node_boats",
                        "relative_path": "docs/runbook.md",
                        "source_backend": "postgres",
                        "title": "Runbook",
                        "summary": "Incident workflow",
                    },
                ],
                "entity_content": [],
                "content_search": [],
            },
            "limitations": [],
        }
    )

    artifact_paths = [
        artifact["relative_path"]
        for artifact in result["support_overview"]["key_artifacts"]
    ]
    assert artifact_paths[:5] == [
        "argocd/api-node-boats/overlays/bg-qa/values.yaml",
        "argocd/api-node-boats/base/values.yaml",
        "argocd/api-node-boats/base/xirsarole.yaml",
        "argocd/api-node-boats/base/dashboards/dashboard-overview-configmap.yaml",
        "specs/openapi.yaml",
    ]
    assert "README.md" in artifact_paths
    assert result["documentation_overview"]["service_summary"].startswith(
        "api-node-boats"
    )
