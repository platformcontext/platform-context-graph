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
