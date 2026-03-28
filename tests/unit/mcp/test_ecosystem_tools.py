"""Focused ecosystem-tool regression tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from platform_context_graph.mcp.tools.handlers import ecosystem
from platform_context_graph.mcp.tools.handlers import ecosystem_support
from platform_context_graph.query.story import build_repository_story_response


class MockResult:
    """Mock Neo4j result wrapper."""

    def __init__(
        self,
        records: list[dict[str, object]] | None = None,
        single_record: dict[str, object] | None = None,
    ) -> None:
        self._records = records or []
        self._single_record = single_record

    def data(self) -> list[dict[str, object]]:
        return self._records

    def single(self) -> dict[str, object] | None:
        return self._single_record


def make_mock_db(query_results: dict[str, MockResult]) -> MagicMock:
    """Build a db manager whose queries are keyed by query substrings."""

    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query: str, **_kwargs: object) -> MockResult:
        for needle, result in query_results.items():
            if needle in query:
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_find_blast_radius_tags_graph_rows_and_adds_consumer_evidence(
    monkeypatch,
) -> None:
    """Blast radius should stay useful even when tier/risk metadata is missing."""

    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
        lambda *_args, **_kwargs: {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
            },
            "consumer_repositories": [
                {
                    "repository": "portal-web",
                    "repo_id": "repository:r_portal_web",
                    "evidence_kinds": ["hostname_reference"],
                    "matched_values": ["api-node-boats.qa.example.com"],
                    "sample_paths": ["src/config.ts"],
                }
            ],
        },
    )
    db = make_mock_db(
        {
            "MATCH (source:Repository)": MockResult(
                records=[
                    {
                        "repo": "orders-worker",
                        "tier": None,
                        "risk": None,
                        "hops": 1,
                    }
                ]
            )
        }
    )

    result = ecosystem.find_blast_radius(db, "api-node-boats", "repository")

    assert result["affected"] == [
        {
            "repo": "orders-worker",
            "tier": None,
            "risk": None,
            "hops": 1,
            "evidence_source": "graph_dependency",
            "inferred": False,
        },
        {
            "repo": "portal-web",
            "repo_id": "repository:r_portal_web",
            "tier": None,
            "risk": None,
            "hops": None,
            "evidence_source": "consumer_reference",
            "evidence_kinds": ["hostname_reference"],
            "matched_values": ["api-node-boats.qa.example.com"],
            "sample_paths": ["src/config.ts"],
            "inferred": True,
        },
    ]
    assert result["affected_count"] == 2
    assert "consumer evidence" in result["note"]


def test_trace_deployment_chain_defaults_to_a_direct_focused_view(
    monkeypatch,
) -> None:
    """The hosted trace should default to direct evidence and explicit truncation."""

    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem_support.repository_queries.get_repository_context",
        lambda *_args, **_kwargs: {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "path": "/repos/api-node-boats",
                "local_path": "/repos/api-node-boats",
            },
            "coverage": {"completeness_state": "complete"},
            "platforms": [
                {
                    "id": "platform:eks:aws:node10",
                    "name": "node10",
                    "kind": "eks",
                    "relationship_type": "RUNS_ON",
                }
            ],
            "deploys_from": [
                {
                    "id": "repository:r_helm",
                    "name": "helm-charts",
                    "relationship_type": "DEPLOYS_FROM",
                }
            ],
            "discovers_config_in": [],
            "provisioned_by": [
                {
                    "id": "repository:r_tf",
                    "name": "terraform-stack-node10",
                    "relationship_type": "PROVISIONED_BY",
                }
            ],
            "provisions_dependencies_for": [
                {
                    "id": "repository:r_docs",
                    "name": "docs-site",
                    "relationship_type": "PROVISIONS_DEPENDENCY_FOR",
                }
            ],
            "deployment_chain": [
                {
                    "relationship_type": "DEPLOYS_FROM",
                    "source_name": "api-node-boats",
                    "target_name": "helm-charts",
                    "target_kind": "Repository",
                },
                {
                    "relationship_type": "RUNS_ON",
                    "source_name": "api-node-boats",
                    "target_name": "node10",
                    "target_kind": "Platform",
                },
                {
                    "relationship_type": "PROVISIONED_BY",
                    "source_name": "terraform-stack-node10",
                    "target_name": "api-node-boats",
                    "target_kind": "Repository",
                },
            ],
            "delivery_paths": [
                {
                    "controller": "GitHub Actions",
                    "delivery_mode": "direct",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["EKS"],
                }
            ],
            "deployment_artifacts": {
                "config_paths": [{"path": "/api/api-node-boats/*"}],
            },
            "consumer_repositories": [
                {
                    "repository": "portal-web",
                    "evidence_kinds": ["hostname_reference"],
                    "sample_paths": ["src/config.ts"],
                }
            ],
            "environments": ["qa"],
            "limitations": [],
        },
    )
    db = make_mock_db(
        {
            "RETURN r.name as name, r.path as path": MockResult(
                single_record={
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                }
            ),
            "MATCH (app:ArgoCDApplication)": MockResult(records=[]),
            "MATCH (app:ArgoCDApplicationSet)": MockResult(records=[]),
            "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(k:K8sResource)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                records=[
                    {
                        "name": "aws_route53_record.api_node_boats",
                        "resource_type": "aws_route53_record",
                        "file": "service.tf",
                        "repository": "api-node-boats",
                    },
                    {
                        "name": "aws_route53_record.shared",
                        "resource_type": "aws_route53_record",
                        "file": "shared.tf",
                        "repository": "terraform-stack-node10",
                    },
                ]
            ),
            "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                records=[
                    {
                        "name": "api_node_boats",
                        "source": "terraform/modules/service",
                        "version": "~> 1.0",
                        "repository": "terraform-stack-node10",
                    }
                ]
            ),
            "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(tg:TerragruntConfig)": MockResult(
                records=[]
            ),
        }
    )

    result = ecosystem_support.trace_deployment_chain(db, "api-node-boats")

    assert result["trace_controls"] == {
        "direct_only": True,
        "max_depth": None,
        "include_related_module_usage": False,
    }
    assert result["deployment_chain"] == [
        {
            "relationship_type": "DEPLOYS_FROM",
            "source_name": "api-node-boats",
            "target_name": "helm-charts",
            "target_kind": "Repository",
        }
    ]
    assert result["terraform_resources"] == [
        {
            "name": "aws_route53_record.api_node_boats",
            "resource_type": "aws_route53_record",
            "file": "service.tf",
            "repository": "api-node-boats",
        }
    ]
    assert result["terraform_modules"] == []
    assert result["truncation"] == {
        "applied": True,
        "omitted_sections": [
            "deployment_chain",
            "terraform_resources",
            "terraform_modules",
            "terragrunt_configs",
            "provisioning_source_chains",
        ],
    }
    assert any(
        "Focused trace shows direct deployment evidence only." in line
        for line in result["story"]
    )
    assert not any(
        "Shared config" in line or "Consumer" in line for line in result["story"]
    )


def test_build_repository_story_response_keeps_direct_story_focused() -> None:
    """Repository stories should keep the concise narrative direct-first."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "repo_slug": "platformcontext/api-node-boats",
                "remote_url": "https://github.com/platformcontext/api-node-boats",
                "has_remote": True,
            },
            "code": {"functions": 8, "classes": 2, "class_methods": 3},
            "hostnames": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "visibility": "public",
                }
            ],
            "api_surface": {"api_versions": ["v3"], "docs_routes": ["/_specs"]},
            "delivery_paths": [
                {
                    "controller": "GitHub Actions",
                    "delivery_mode": "direct",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["EKS"],
                }
            ],
            "deployment_artifacts": {
                "config_paths": [{"path": "/api/api-node-boats/*"}]
            },
            "consumer_repositories": [
                {
                    "repository": "portal-web",
                    "evidence_kinds": ["hostname_reference"],
                    "sample_paths": ["src/config.ts"],
                }
            ],
            "limitations": [],
        }
    )

    assert result["deployment_overview"]["trace_controls"] == {
        "direct_only": True,
        "include_shared_config": False,
        "include_consumers": False,
    }
    assert result["deployment_overview"]["trace_limitations"] == {
        "omitted_sections": [
            "shared_config_paths",
            "consumer_repositories",
        ],
        "reason": "Keep the repository story focused on direct deployment evidence.",
    }
    assert result["deployment_overview"]["topology_story"] != result["story"]
    assert any(
        "Shared config" in line or "Consumer repositories" in line
        for line in result["deployment_overview"]["topology_story"]
    )
    assert not any(
        "Shared config" in line or "Consumer repositories" in line
        for line in result["story"]
    )
