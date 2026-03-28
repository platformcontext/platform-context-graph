"""Targeted hosted ecosystem gap tests for MCP-facing query helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from platform_context_graph.mcp.tools.ecosystem import ECOSYSTEM_TOOLS
from platform_context_graph.mcp.tools.handlers import ecosystem
from platform_context_graph.query.infra import search_infra_resources


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


def test_search_infra_resources_prefers_specific_crossplane_classification() -> None:
    """Claim-like K8s hits should move to Crossplane instead of staying generic."""

    db = make_mock_db(
        {
            "WITH k, f, repo, split(coalesce(k.api_version, ''), '/')[0] as api_group": MockResult(
                records=[
                    {
                        "name": "api-node-boats",
                        "kind": "XIRSARole",
                        "namespace": "boats",
                        "api_version": "aws.platform.example/v1alpha1",
                        "repository": "helm-charts",
                        "file": "argocd/api-node-boats/base/xirsarole.yaml",
                    }
                ]
            ),
            "MATCH (k:K8sResource)": MockResult(
                records=[
                    {
                        "name": "api-node-boats",
                        "kind": "XIRSARole",
                        "namespace": "boats",
                        "api_version": "aws.platform.example/v1alpha1",
                        "repository": "helm-charts",
                        "file": "argocd/api-node-boats/base/xirsarole.yaml",
                    },
                    {
                        "name": "api-node-boats",
                        "kind": "Deployment",
                        "namespace": "boats",
                        "file": "k8s/deployment.yaml",
                    },
                ]
            ),
            "MATCH (a:ArgoCDApplication)": MockResult(records=[]),
            "MATCH (a:ArgoCDApplicationSet)": MockResult(records=[]),
            "MATCH (x:CrossplaneXRD)": MockResult(records=[]),
            "MATCH (c:CrossplaneClaim)": MockResult(records=[]),
            "MATCH (h:HelmChart)": MockResult(records=[]),
            "MATCH (t:TerraformResource)": MockResult(records=[]),
        }
    )

    result = search_infra_resources(db, query="api-node-boats", limit=10)

    assert result["results"]["crossplane_claims"] == [
        {
            "name": "api-node-boats",
            "kind": "XIRSARole",
            "namespace": "boats",
            "api_version": "aws.platform.example/v1alpha1",
            "repository": "helm-charts",
            "file": "argocd/api-node-boats/base/xirsarole.yaml",
        }
    ]
    assert result["results"]["k8s_resources"] == [
        {
            "name": "api-node-boats",
            "kind": "Deployment",
            "namespace": "boats",
            "file": "k8s/deployment.yaml",
        }
    ]


def test_find_blast_radius_augments_graph_results_with_consumer_evidence(
    monkeypatch,
) -> None:
    """Repository blast radius should include concrete consumer repositories."""

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


def test_trace_deployment_chain_supports_direct_filters_and_truncation(
    monkeypatch,
) -> None:
    """Deployment traces should accept focused shaping controls."""

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

    result = ecosystem.trace_deployment_chain(
        db,
        "api-node-boats",
        direct_only=True,
        max_depth=1,
        include_related_module_usage=False,
    )

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
    assert result["trace_controls"] == {
        "direct_only": True,
        "max_depth": 1,
        "include_related_module_usage": False,
    }
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


def test_trace_deployment_chain_tool_schema_advertises_shaping_controls() -> None:
    """The MCP schema should surface the hosted trace-shaping knobs."""

    properties = ECOSYSTEM_TOOLS["trace_deployment_chain"]["inputSchema"]["properties"]

    assert properties["direct_only"]["default"] is True
    assert properties["max_depth"]["type"] == "integer"
    assert properties["include_related_module_usage"]["default"] is False
