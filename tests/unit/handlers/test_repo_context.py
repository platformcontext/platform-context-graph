"""Tests for get_repo_context handler and degradation behavior."""

from unittest.mock import MagicMock

from platform_context_graph.mcp.tools.handlers.ecosystem import (
    find_blast_radius,
    get_ecosystem_overview,
    get_repo_context,
    get_repo_summary,
    trace_deployment_chain,
)


class MockRecord:
    """Mock for a single Neo4j record."""

    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockResult:
    """Mock for Neo4j query result."""

    def __init__(self, records=None, single_record=None):
        self._records = records or []
        self._single_record = single_record

    def single(self):
        return self._single_record

    def data(self):
        return self._records


def make_mock_db(query_results):
    """Create a mock db_manager where session.run returns based on query content.

    Args:
        query_results: Dict mapping query substring to MockResult.
    """
    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query, **kwargs):
        for substr, result in query_results.items():
            if substr in query:
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


class TestGetRepoContext:
    """Test get_repo_context handler."""

    def test_returns_error_when_repo_not_found(self):
        db = make_mock_db(
            {
                "MATCH (r:Repository)": MockResult(single_record=None),
            }
        )
        result = get_repo_context(db, "nonexistent")
        assert "error" in result
        assert "not found" in result["error"]

    def test_returns_structured_response(self):
        code_record = MockRecord({"functions": 10, "classes": 3})
        graph_counts_record = MockRecord(
            {
                "root_file_count": 0,
                "root_directory_count": 0,
                "file_count": 3,
                "top_level_function_count": 10,
                "class_method_count": 0,
                "total_function_count": 10,
                "class_count": 3,
                "module_count": 0,
            }
        )
        tier_record = None
        deps_record = MockRecord({"dependencies": []})
        dependents_record = MockRecord({"dependents": []})

        db = make_mock_db(
            {
                "coalesce(r[$local_path_key], r.path) as local_path": MockResult(
                    records=[
                        {
                            "id": "repository:r_ab12cd34",
                            "name": "my-api",
                            "path": "/repos/my-api",
                            "local_path": "/repos/my-api",
                            "remote_url": "https://github.com/platformcontext/my-api",
                            "repo_slug": "platformcontext/my-api",
                            "has_remote": True,
                        }
                    ]
                ),
                "split(f.name": MockResult(
                    records=[
                        {"file": "main.py", "ext": "py"},
                        {"file": "utils.py", "ext": "py"},
                        {"file": "deploy.yaml", "ext": "yaml"},
                    ]
                ),
                "root_file_count": MockResult(single_record=graph_counts_record),
                "count(DISTINCT fn)": MockResult(single_record=code_record),
                "fn.name IN": MockResult(records=[]),
                "K8sResource": MockResult(records=[]),
                "TerraformResource": MockResult(records=[]),
                "TerraformModule": MockResult(records=[]),
                "TerraformVariable": MockResult(records=[]),
                "TerraformOutput": MockResult(records=[]),
                "ArgoCDApplication": MockResult(records=[]),
                "ArgoCDApplicationSet": MockResult(records=[]),
                "CrossplaneXRD": MockResult(records=[]),
                "CrossplaneComposition": MockResult(records=[]),
                "CrossplaneClaim": MockResult(records=[]),
                "HelmChart": MockResult(records=[]),
                "HelmValues": MockResult(records=[]),
                "KustomizeOverlay": MockResult(records=[]),
                "TerragruntConfig": MockResult(records=[]),
                "type(rel) IN": MockResult(records=[]),
                "Tier": MockResult(single_record=tier_record),
                "MATCH (r:Repository)-[rel]->(dep:Repository)": MockResult(single_record=deps_record),
                "<-[rel]-(dep:Repository)": MockResult(single_record=dependents_record),
            }
        )

        result = get_repo_context(db, "my-api")
        assert "error" not in result
        assert result["repository"]["name"] == "my-api"
        assert result["repository"]["file_count"] == 3
        assert result["code"]["functions"] == 10
        assert result["code"]["classes"] == 3
        assert "python" in result["code"]["languages"]
        assert result["infrastructure"] == {}
        assert result["relationships"] == []
        assert result["ecosystem"] is None


class TestGracefulDegradation:
    """Test standalone mode behavior without ecosystem manifest."""

    def test_ecosystem_overview_standalone_mode(self):
        eco_record = MockRecord({"name": None, "org": None})
        db = make_mock_db(
            {
                "Ecosystem": MockResult(single_record=eco_record),
                "Tier": MockResult(records=[]),
                "Repository": MockResult(records=[]),
                "K8sResource": MockResult(
                    single_record=MockRecord(
                        {
                            "k8s": 5,
                            "argocd": 0,
                            "xrds": 0,
                            "terraform": 0,
                            "helm": 0,
                        }
                    )
                ),
                "SOURCES_FROM": MockResult(
                    single_record=MockRecord(
                        {
                            "sources_from": 0,
                            "deploys": 0,
                            "satisfied_by": 0,
                            "depends_on": 0,
                        }
                    )
                ),
            }
        )
        result = get_ecosystem_overview(db)
        assert result["mode"] == "standalone"
        assert "No ecosystem manifest" in result["note"]
        assert "ecosystem" not in result

    def test_ecosystem_overview_with_manifest(self):
        eco_record = MockRecord({"name": "my-platform", "org": "myorg"})
        db = make_mock_db(
            {
                "Ecosystem": MockResult(single_record=eco_record),
                "Tier": MockResult(records=[]),
                "Repository": MockResult(records=[]),
                "K8sResource": MockResult(
                    single_record=MockRecord(
                        {
                            "k8s": 0,
                            "argocd": 0,
                            "xrds": 0,
                            "terraform": 0,
                            "helm": 0,
                        }
                    )
                ),
                "SOURCES_FROM": MockResult(
                    single_record=MockRecord(
                        {
                            "sources_from": 0,
                            "deploys": 0,
                            "satisfied_by": 0,
                            "depends_on": 0,
                        }
                    )
                ),
            }
        )
        result = get_ecosystem_overview(db)
        assert result["ecosystem"]["name"] == "my-platform"
        assert "mode" not in result


def test_trace_deployment_chain_uses_repo_contains_for_repo_to_file_lookups(
    monkeypatch,
):
    """Deployment-chain repo/file lookups should use REPO_CONTAINS."""

    recorded_queries: list[str] = []

    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem_support.repository_queries.get_repository_context",
        lambda *_args, **_kwargs: {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "path": "/repos/api-node-boats",
                "local_path": "/repos/api-node-boats",
            },
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "platforms": [],
            "summary": {},
            "coverage": None,
            "limitations": [],
        },
    )

    db = make_mock_db({})
    session = db.get_driver.return_value.session.return_value

    def recording_run(query, **kwargs):
        del kwargs
        recorded_queries.append(query)
        if "MATCH (r:Repository)" in query and "RETURN r.name as name" in query:
            return MockResult(single_record={"name": "api-node-boats", "path": "/repos/api-node-boats"})
        return MockResult(records=[])

    session.run = recording_run

    result = trace_deployment_chain(db, "api-node-boats")

    assert "error" not in result
    assert any(
        "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(k:K8sResource)"
        in q
        for q in recorded_queries
    )
    assert any(
        "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)"
        in q
        for q in recorded_queries
    )
    assert any(
        "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(tf:TerraformResource)"
        in q
        for q in recorded_queries
    )



class TestRepoSummary:
    """Test repo summary shaping and truthfulness notes."""

    def test_repo_summary_omits_tier_when_null(self, monkeypatch):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_summary123",
                    "name": "my-repo",
                    "path": "/repos/my-repo",
                    "file_count": 0,
                    "files_by_extension": {},
                },
                "code": {"functions": 0, "classes": 0},
                "infrastructure": {},
                "ecosystem": {
                    "tier": None,
                    "risk_level": None,
                    "dependencies": [],
                    "dependents": [],
                },
                "coverage": None,
                "platforms": [],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "environments": [],
                "limitations": [],
                "relationships": [],
            },
        )
        result = get_repo_summary(make_mock_db({}), "my-repo")
        assert "tier" not in result

    def test_repo_summary_surfaces_partial_coverage_note(self, monkeypatch):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_partial123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                    "file_count": 12,
                    "discovered_file_count": 196,
                    "files_by_extension": {"json": 12},
                },
                "code": {"functions": 0, "classes": 0},
                "infrastructure": {},
                "ecosystem": None,
                "coverage": {
                    "run_id": "run-123",
                    "completeness_state": "graph_partial",
                    "graph_available": True,
                    "server_content_available": False,
                    "discovered_file_count": 196,
                    "graph_recursive_file_count": 12,
                    "content_file_count": 12,
                    "content_entity_count": 24,
                    "graph_gap_count": 184,
                    "content_gap_count": 0,
                },
                "platforms": [],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "environments": [],
                "limitations": ["graph_partial", "content_partial"],
            },
        )

        result = get_repo_summary(make_mock_db({}), "api-node-boats")

        assert result["file_count"] == 196
        assert result["coverage"]["completeness_state"] == "graph_partial"
        assert result["coverage"]["graph_gap_count"] == 184
        assert "partial" in result["note"].lower()

    def test_repo_summary_surfaces_runtime_context_and_limitation_codes(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                    "file_count": 196,
                    "files_by_extension": {"yaml": 43, "js": 77},
                },
                "code": {"functions": 12, "classes": 1},
                "infrastructure": {"terraform_modules": []},
                "ecosystem": {
                    "tier": None,
                    "risk_level": None,
                    "dependencies": ["terraform-stack-ecs"],
                    "dependents": [],
                },
                "coverage": {
                    "completeness_state": "complete",
                    "discovered_file_count": 196,
                    "graph_recursive_file_count": 196,
                    "content_file_count": 196,
                    "content_entity_count": 240,
                    "graph_gap_count": 0,
                    "content_gap_count": 0,
                    "server_content_available": True,
                },
                "platforms": [
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "relationship_type": "RUNS_ON",
                    }
                ],
                "deploys_from": [
                    {
                        "id": "repository:r_helm123",
                        "name": "helm-charts",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ],
                "discovers_config_in": [],
                "provisioned_by": [
                    {
                        "id": "repository:r_terraform123",
                        "name": "terraform-stack-ecs",
                        "relationship_type": "PROVISIONED_BY",
                    }
                ],
                "provisions_dependencies_for": [],
                "environments": ["prod"],
                "delivery_workflows": {
                    "github_actions": {
                        "commands": [
                            {
                                "command": "deploy-eks",
                                "workflow": "node-api-deploy-eks.yml",
                                "delivery_mode": "eks_gitops",
                            }
                        ]
                    }
                },
                "delivery_paths": [
                    {
                        "path_kind": "gitops",
                        "controller": "github_actions",
                        "delivery_mode": "eks_gitops",
                        "commands": ["deploy-eks"],
                        "supporting_workflows": ["node-api-deploy-eks.yml"],
                        "automation_repositories": [
                            "boatsgroup/core-engineering-automation"
                        ],
                        "platform_kinds": ["eks"],
                        "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
                        "deployment_sources": ["helm-charts"],
                        "config_sources": [],
                        "provisioning_repositories": [],
                        "environments": ["bg-qa"],
                        "summary": "GitHub Actions drives a GitOps deployment path through helm-charts onto EKS platforms.",
                    }
                ],
                "deployment_artifacts": {
                    "charts": [
                        {
                            "repo_url": "boatsgroup.pe.jfrog.io",
                            "chart": "bg-helm/api-node-template",
                            "version": "0.2.1",
                            "release_name": "api-node-boats",
                            "namespace": "api-node",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                            "environment": "bg-qa",
                        }
                    ],
                    "images": [
                        {
                            "repository": "048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                            "tag": "3.21.0",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                            "environment": "bg-qa",
                        }
                    ],
                    "kustomize_resources": [
                        {
                            "resource_path": "argocd/api-node-boats/base/xirsarole.yaml",
                            "kind": "XIRSARole",
                            "name": "api-node-boats",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/kustomization.yaml",
                            "environment": None,
                        }
                    ],
                    "kustomize_patches": [
                        {
                            "patch_path": "argocd/api-node-boats/overlays/bg-qa/xirsarole-patch.yaml",
                            "target_kind": "XIRSARole",
                            "target_name": "api-node-boats",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/kustomization.yaml",
                            "environment": "bg-qa",
                        }
                    ],
                    "config_paths": [
                        {
                            "path": "/configd/api-node-boats/*",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                            "environment": None,
                        },
                        {
                            "path": "/api/api-node-boats/*",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                            "environment": None,
                        },
                        {
                            "path": "/configd/api-node-boats/*",
                            "source_repo": "terraform-stack-node10",
                            "relative_path": "shared/iam.tf",
                            "environment": None,
                        },
                    ],
                    "service_ports": [
                        {
                            "port": "3081",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/values.yaml",
                            "environment": None,
                        }
                    ],
                    "gateways": [
                        {
                            "name": "envoy-internal",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                            "environment": "bg-qa",
                        }
                    ],
                },
                "api_surface": {
                    "spec_files": [{"relative_path": "specs/index.yaml"}],
                    "docs_routes": ["/_specs"],
                    "api_versions": ["v3"],
                },
                "hostnames": [
                    {"hostname": "api-node-boats.qa.bgrp.io", "visibility": "public"}
                ],
                "consumer_repositories": [
                    {
                        "repository": "automate-yachtworld",
                        "repo_id": "repository:r_yachtworld123",
                        "evidence_kinds": ["hostname_reference"],
                        "matched_values": ["api-node-boats.qa.bgrp.io"],
                        "sample_paths": ["group_vars/qa/api.yml"],
                    }
                ],
                "limitations": ["dns_unknown", "entrypoint_unknown"],
                "relationships": [],
            },
        )

        result = get_repo_summary(make_mock_db({}), "api-node-boats")

        assert result["name"] == "api-node-boats"
        assert result["platforms"][0]["kind"] == "ecs"
        assert result["deploys_from"][0]["name"] == "helm-charts"
        assert result["dependencies"] == ["terraform-stack-ecs"]
        assert result["delivery_workflows"]["github_actions"]["commands"] == [
            {
                "command": "deploy-eks",
                "workflow": "node-api-deploy-eks.yml",
                "delivery_mode": "eks_gitops",
            }
        ]
        assert result["delivery_paths"][0]["path_kind"] == "gitops"
        assert result["delivery_paths"][0]["deployment_sources"] == ["helm-charts"]
        assert result["deployment_artifacts"]["images"][0]["tag"] == "3.21.0"
        assert result["consumer_repositories"] == [
            {
                "repository": "automate-yachtworld",
                "repo_id": "repository:r_yachtworld123",
                "evidence_kinds": ["hostname_reference"],
                "matched_values": ["api-node-boats.qa.bgrp.io"],
                "sample_paths": ["group_vars/qa/api.yml"],
            }
        ]
        assert result["deployment_overview"] == {
            "internet_entrypoints": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "visibility": "public",
                }
            ],
            "internal_entrypoints": [],
            "api_surface": {
                "docs_routes": ["/_specs"],
                "api_versions": ["v3"],
            },
            "runtime_platforms": [
                {
                    "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    "kind": "ecs",
                    "provider": "aws",
                    "environment": "prod",
                    "name": "node10",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "summary": "GitHub Actions drives a GitOps deployment path through helm-charts onto EKS platforms.",
                    "automation_repositories": [
                        "boatsgroup/core-engineering-automation"
                    ],
                    "platform_kinds": ["eks"],
                    "deployment_sources": ["helm-charts"],
                    "config_sources": [],
                    "provisioning_repositories": [],
                    "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
                    "environments": ["bg-qa"],
                }
            ],
            "deployment_story": [
                "GitHub Actions via boatsgroup/core-engineering-automation deploys from helm-charts onto EKS in bg-qa."
            ],
            "topology_story": [
                "Public entrypoints: api-node-boats.qa.bgrp.io.",
                "API surface exposes versions v3 and docs routes /_specs.",
                "GitHub Actions via boatsgroup/core-engineering-automation deploys from helm-charts onto EKS in bg-qa.",
                "Shared config paths include /configd/api-node-boats/* across helm-charts, terraform-stack-node10.",
                "Consumer-only repositories include automate-yachtworld.",
            ],
            "consumer_repositories": [
                {
                    "repository": "automate-yachtworld",
                    "evidence_kinds": ["hostname_reference"],
                    "sample_paths": ["group_vars/qa/api.yml"],
                }
            ],
            "shared_config_paths": [
                {
                    "path": "/configd/api-node-boats/*",
                    "source_repositories": [
                        "helm-charts",
                        "terraform-stack-node10",
                    ],
                }
            ],
                "deployment_artifacts": {
                    "charts": [
                        {
                            "repo_url": "boatsgroup.pe.jfrog.io",
                        "chart": "bg-helm/api-node-template",
                        "version": "0.2.1",
                        "release_name": "api-node-boats",
                        "namespace": "api-node",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/config.yaml",
                        "environment": "bg-qa",
                    }
                ],
                "images": [
                    {
                        "repository": "048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                        "tag": "3.21.0",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                            "environment": "bg-qa",
                        }
                    ],
                    "kustomize_resources": [
                        {
                            "resource_path": "argocd/api-node-boats/base/xirsarole.yaml",
                            "kind": "XIRSARole",
                            "name": "api-node-boats",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/kustomization.yaml",
                            "environment": None,
                        }
                    ],
                    "kustomize_patches": [
                        {
                            "patch_path": "argocd/api-node-boats/overlays/bg-qa/xirsarole-patch.yaml",
                            "target_kind": "XIRSARole",
                            "target_name": "api-node-boats",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/kustomization.yaml",
                            "environment": "bg-qa",
                        }
                    ],
                    "config_paths": [
                        {
                            "path": "/configd/api-node-boats/*",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                            "environment": None,
                        },
                        {
                            "path": "/api/api-node-boats/*",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/base/xirsarole.yaml",
                            "environment": None,
                        },
                        {
                            "path": "/configd/api-node-boats/*",
                            "source_repo": "terraform-stack-node10",
                            "relative_path": "shared/iam.tf",
                            "environment": None,
                        },
                    ],
                    "service_ports": [
                        {
                            "port": "3081",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/values.yaml",
                        "environment": None,
                    }
                ],
                "gateways": [
                    {
                        "name": "envoy-internal",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "environment": "bg-qa",
                    }
                ],
            },
            "deployment_controllers": ["github_actions"],
        }
        assert result["api_surface"]["docs_routes"] == ["/_specs"]
        assert result["hostnames"][0]["hostname"] == "api-node-boats.qa.bgrp.io"
        assert result["limitations"] == ["dns_unknown", "entrypoint_unknown"]

    def test_repo_summary_notes_config_environments_when_runtime_unknown(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                    "file_count": 196,
                    "discovered_file_count": 196,
                    "files_by_extension": {"json": 12, "js": 77},
                },
                "code": {"functions": 12, "classes": 1},
                "infrastructure": {},
                "ecosystem": {"dependencies": [], "dependents": []},
                "coverage": {
                    "completeness_state": "complete",
                    "discovered_file_count": 196,
                    "graph_recursive_file_count": 196,
                    "content_file_count": 196,
                    "content_entity_count": 240,
                    "graph_gap_count": 0,
                    "content_gap_count": 0,
                    "server_content_available": True,
                },
                "platforms": [],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "environments": [],
                "observed_config_environments": ["bg-qa", "prod"],
                "api_surface": {},
                "hostnames": [
                    {
                        "hostname": "api-node-boats.qa.bgrp.io",
                        "environment": "bg-qa",
                        "visibility": "public",
                    }
                ],
                "limitations": [],
                "relationships": [],
            },
        )

        result = get_repo_summary(make_mock_db({}), "api-node-boats")

        assert "note" in result
        assert "bg-qa, prod" in result["note"]
        assert "runtime evidence" in result["note"].lower()

    def test_repo_summary_notes_config_environments_beyond_runtime(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                    "file_count": 196,
                    "discovered_file_count": 196,
                    "files_by_extension": {"json": 12, "js": 77},
                },
                "code": {"functions": 12, "classes": 1},
                "infrastructure": {},
                "ecosystem": {"dependencies": [], "dependents": []},
                "coverage": {
                    "completeness_state": "complete",
                    "discovered_file_count": 196,
                    "graph_recursive_file_count": 196,
                    "content_file_count": 196,
                    "content_entity_count": 240,
                    "graph_gap_count": 0,
                    "content_gap_count": 0,
                    "server_content_available": True,
                },
                "platforms": [
                    {
                        "id": "platform:eks:aws:cluster/bg-qa",
                        "name": "bg-qa",
                        "kind": "eks",
                        "provider": "aws",
                        "environment": "bg-qa",
                        "relationship_type": "RUNS_ON",
                    }
                ],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "environments": ["bg-qa"],
                "observed_config_environments": ["bg-qa", "prod"],
                "api_surface": {},
                "hostnames": [
                    {
                        "hostname": "api-node-boats.qa.bgrp.io",
                        "environment": "bg-qa",
                        "visibility": "public",
                    },
                    {
                        "hostname": "api-node-boats.prod.bgrp.io",
                        "environment": "prod",
                        "visibility": "public",
                    },
                ],
                "limitations": [],
                "relationships": [],
            },
        )

        result = get_repo_summary(make_mock_db({}), "api-node-boats")

        assert "note" in result
        assert "confirmed runtime environments: bg-qa" in result["note"].lower()
        assert "configuration also references: prod" in result["note"].lower()

    def test_repo_summary_notes_pending_finalization_truthfully(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                    "file_count": 199,
                    "discovered_file_count": 199,
                    "files_by_extension": {"yaml": 84, "js": 251},
                },
                "code": {"functions": 347, "classes": 0},
                "infrastructure": {},
                "ecosystem": {"dependencies": [], "dependents": []},
                "coverage": {
                    "completeness_state": "complete",
                    "finalization_status": "pending",
                    "discovered_file_count": 199,
                    "graph_recursive_file_count": 199,
                    "content_file_count": 199,
                    "content_entity_count": 3106,
                    "graph_gap_count": 0,
                    "content_gap_count": 0,
                    "server_content_available": True,
                },
                "platforms": [],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "environments": [],
                "observed_config_environments": [],
                "api_surface": {},
                "hostnames": [],
                "limitations": ["finalization_incomplete"],
                "relationships": [],
            },
        )

        result = get_repo_summary(make_mock_db({}), "api-node-boats")

        assert "note" in result
        assert "finalization" in result["note"].lower()
        assert "incomplete" in result["note"].lower()

    def test_blast_radius_adds_note_when_tier_null(self):
        db = make_mock_db(
            {
                "Repository": MockResult(
                    records=[
                        {"repo": "service-a", "tier": None, "risk": None, "hops": 1},
                    ]
                ),
            }
        )
        result = find_blast_radius(db, "my-lib", "repository")
        assert "note" in result
        assert "ecosystem manifest" in result["note"]


class TestTraceDeploymentChain:
    """Test deployment traces for repository and ApplicationSet-backed services."""

    def test_returns_applicationset_backed_chain(self, monkeypatch):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_search123",
                    "name": "api-node-search",
                    "path": "/repos/api-node-search",
                },
                "coverage": None,
                "platforms": [],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "deployment_chain": [],
                "environments": [],
                "limitations": [],
            },
        )
        repo_record = MockRecord({"name": "api-node-search", "path": "/repos/api-node-search"})

        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "MATCH (app:ArgoCDApplication)": MockResult(records=[]),
                "MATCH (app:ArgoCDApplicationSet)": MockResult(
                    records=[
                        {
                            "app_name": "api-node-search",
                            "project": "{{.argocd.project}}",
                            "namespace": "argocd",
                            "dest_namespace": "{{.helm.namespace}}",
                            "source_repos": "https://github.com/boatsgroup/helm-charts",
                            "source_paths": "argocd/api-node-search/overlays/*/config.yaml",
                            "source_roots": "argocd/api-node-search/",
                        }
                    ]
                ),
                "repo.id IN $source_repo_ids OR repo.name IN $source_repo_names": MockResult(
                    records=[
                        {
                            "name": "api-node-search",
                            "kind": "XIRSARole",
                            "namespace": "",
                            "file": "argocd/api-node-search/base/xirsarole.yaml",
                            "repository": "helm-charts",
                            "deployed_by": "api-node-search",
                        }
                    ]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                    records=[]
                ),
            }
        )

        result = trace_deployment_chain(db, "api-node-search")

        assert result["repository"]["name"] == "api-node-search"
        assert result["argocd_applications"] == []
        assert result["argocd_applicationsets"] == [
            {
                "app_name": "api-node-search",
                "project": "{{.argocd.project}}",
                "namespace": "argocd",
                "dest_namespace": "{{.helm.namespace}}",
                "source_repos": "https://github.com/boatsgroup/helm-charts",
                "source_paths": "argocd/api-node-search/overlays/*/config.yaml",
                "source_roots": "argocd/api-node-search/",
            }
        ]
        assert result["k8s_resources"] == [
            {
                "name": "api-node-search",
                "kind": "XIRSARole",
                "namespace": "",
                "file": "argocd/api-node-search/base/xirsarole.yaml",
                "repository": "helm-charts",
                "deployed_by": "api-node-search",
            }
        ]

    def test_trace_deployment_chain_surfaces_runtime_context_and_limitations(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                },
                "coverage": {
                    "completeness_state": "complete",
                    "graph_gap_count": 0,
                    "content_gap_count": 0,
                },
                "platforms": [
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "relationship_type": "RUNS_ON",
                    }
                ],
                "deploys_from": [
                    {
                        "id": "repository:r_helm123",
                        "name": "helm-charts",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ],
                "discovers_config_in": [],
                "provisioned_by": [
                    {
                        "id": "repository:r_tf123",
                        "name": "terraform-stack-ecs",
                        "relationship_type": "PROVISIONED_BY",
                    }
                ],
                "provisions_dependencies_for": [],
                "deployment_chain": [
                    {
                        "relationship_type": "RUNS_ON",
                        "target_name": "node10",
                        "target_kind": "Platform",
                    }
                ],
                "environments": ["prod"],
                "delivery_workflows": {
                    "github_actions": {
                        "commands": [
                            {
                                "command": "deploy",
                                "workflow": "node-api-cd.yml",
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
                        "commands": ["deploy"],
                        "supporting_workflows": ["node-api-cd.yml"],
                        "automation_repositories": [
                            "boatsgroup/core-engineering-automation"
                        ],
                        "platform_kinds": ["ecs"],
                        "platforms": ["platform:ecs:aws:cluster/node10:prod:us-east-1"],
                        "deployment_sources": [],
                        "config_sources": [],
                        "provisioning_repositories": ["terraform-stack-ecs"],
                        "environments": ["prod"],
                        "summary": "GitHub Actions drives a direct deployment path through terraform-stack-ecs onto ECS platforms.",
                    }
                ],
                "deployment_artifacts": {
                    "images": [
                        {
                            "repository": "048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                            "tag": "3.21.0",
                            "source_repo": "helm-charts",
                            "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                            "environment": "bg-qa",
                        }
                    ]
                },
                "api_surface": {"docs_routes": ["/_specs"], "api_versions": ["v3"]},
                "hostnames": [
                    {"hostname": "api-node-boats.qa.bgrp.io", "visibility": "public"}
                ],
                "limitations": ["dns_unknown", "entrypoint_unknown"],
            },
        )
        repo_record = MockRecord({"name": "api-node-boats", "path": "/repos/api-node-boats"})
        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "MATCH (app:ArgoCDApplication)": MockResult(records=[]),
                "MATCH (app:ArgoCDApplicationSet)": MockResult(records=[]),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                    records=[]
                ),
            }
        )

        result = trace_deployment_chain(db, "api-node-boats")

        assert result["repository"]["name"] == "api-node-boats"
        assert result["platforms"][0]["kind"] == "ecs"
        assert result["deploys_from"][0]["name"] == "helm-charts"
        assert result["provisioned_by"][0]["name"] == "terraform-stack-ecs"
        assert result["environments"] == ["prod"]
        assert result["delivery_workflows"]["github_actions"]["commands"] == [
            {
                "command": "deploy",
                "workflow": "node-api-cd.yml",
                "delivery_mode": "continuous_deployment",
            }
        ]
        assert result["delivery_paths"][0]["path_kind"] == "direct"
        assert result["delivery_paths"][0]["provisioning_repositories"] == [
            "terraform-stack-ecs"
        ]
        assert result["deployment_artifacts"]["images"][0]["repository"].endswith(
            "/api-node-boats"
        )
        assert result["deployment_overview"] == {
            "internet_entrypoints": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "visibility": "public",
                }
            ],
            "internal_entrypoints": [],
            "api_surface": {
                "docs_routes": ["/_specs"],
                "api_versions": ["v3"],
            },
            "runtime_platforms": [
                {
                    "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    "kind": "ecs",
                    "provider": "aws",
                    "environment": "prod",
                    "name": "node10",
                }
            ],
            "delivery_paths": [
                {
                    "path_kind": "direct",
                    "controller": "github_actions",
                    "delivery_mode": "continuous_deployment",
                    "summary": "GitHub Actions drives a direct deployment path through terraform-stack-ecs onto ECS platforms.",
                    "automation_repositories": [
                        "boatsgroup/core-engineering-automation"
                    ],
                    "platform_kinds": ["ecs"],
                    "deployment_sources": [],
                    "config_sources": [],
                    "provisioning_repositories": ["terraform-stack-ecs"],
                    "platforms": [
                        "platform:ecs:aws:cluster/node10:prod:us-east-1"
                    ],
                    "environments": ["prod"],
                }
            ],
            "deployment_story": [
                "GitHub Actions via boatsgroup/core-engineering-automation deploys through terraform-stack-ecs onto ECS in prod."
            ],
            "topology_story": [
                "Public entrypoints: api-node-boats.qa.bgrp.io.",
                "API surface exposes versions v3 and docs routes /_specs.",
                "GitHub Actions via boatsgroup/core-engineering-automation deploys through terraform-stack-ecs onto ECS in prod.",
            ],
            "deployment_artifacts": {
                "images": [
                    {
                        "repository": "048922418463.dkr.ecr.us-east-1.amazonaws.com/api-node-boats",
                        "tag": "3.21.0",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "environment": "bg-qa",
                    }
                ]
            },
            "deployment_controllers": ["github_actions"],
        }
        assert result["api_surface"]["api_versions"] == ["v3"]
        assert result["hostnames"][0]["hostname"] == "api-node-boats.qa.bgrp.io"
        assert result["limitations"] == ["dns_unknown", "entrypoint_unknown"]

    def test_trace_deployment_chain_uses_canonical_source_repositories(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                },
                "coverage": {
                    "completeness_state": "complete",
                    "graph_gap_count": 0,
                    "content_gap_count": 0,
                },
                "platforms": [
                    {
                        "id": "platform:ecs:aws:cluster/node10:none:none",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "relationship_type": "RUNS_ON",
                    }
                ],
                "deploys_from": [
                    {
                        "id": "repository:r_helm123",
                        "name": "helm-charts",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ],
                "discovers_config_in": [],
                "provisioned_by": [
                    {
                        "id": "repository:r_tf123",
                        "name": "terraform-stack-node10",
                        "relationship_type": "PROVISIONED_BY",
                    }
                ],
                "provisions_dependencies_for": [],
                "deployment_chain": [],
                "environments": ["bg-qa"],
                "api_surface": {"api_versions": ["v3"]},
                "hostnames": [],
                "limitations": [],
            },
        )
        repo_record = MockRecord({"name": "api-node-boats", "path": "/repos/api-node-boats"})
        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "MATCH (app:ArgoCDApplication)": MockResult(records=[]),
                "MATCH (app:ArgoCDApplicationSet)": MockResult(
                    records=[
                        {
                            "app_name": "api-node-boats",
                            "project": "{{.argocd.project}}",
                            "namespace": "argocd",
                            "dest_namespace": "{{.helm.namespace}}",
                            "source_repos": "https://github.com/boatsgroup/helm-charts",
                            "source_paths": "argocd/api-node-boats/overlays/*/config.yaml",
                            "source_roots": "argocd/api-node-boats/",
                        }
                    ]
                ),
                "repo.id IN $source_repo_ids OR repo.name IN $source_repo_names": MockResult(
                    records=[
                        {
                            "name": "api-node-boats",
                            "kind": "XIRSARole",
                            "namespace": "",
                            "file": "argocd/api-node-boats/base/xirsarole.yaml",
                            "repository": "helm-charts",
                            "deployed_by": "api-node-boats",
                        }
                    ]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                    records=[]
                ),
            }
        )

        result = trace_deployment_chain(db, "api-node-boats")

        assert result["argocd_applications"] == []
        assert result["argocd_applicationsets"] == [
            {
                "app_name": "api-node-boats",
                "project": "{{.argocd.project}}",
                "namespace": "argocd",
                "dest_namespace": "{{.helm.namespace}}",
                "source_repos": "https://github.com/boatsgroup/helm-charts",
                "source_paths": "argocd/api-node-boats/overlays/*/config.yaml",
                "source_roots": "argocd/api-node-boats/",
            }
        ]
        assert result["k8s_resources"] == [
            {
                "name": "api-node-boats",
                "kind": "XIRSARole",
                "namespace": "",
                "file": "argocd/api-node-boats/base/xirsarole.yaml",
                "repository": "helm-charts",
                "deployed_by": "api-node-boats",
            }
        ]

    def test_trace_deployment_chain_ignores_shared_source_repo_overmatch(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                },
                "coverage": None,
                "platforms": [],
                "deploys_from": [
                    {
                        "id": "repository:r_helm123",
                        "name": "helm-charts",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ],
                "discovers_config_in": [],
                "provisioned_by": [],
                "provisions_dependencies_for": [],
                "deployment_chain": [],
                "environments": [],
                "limitations": [],
            },
        )
        repo_record = MockRecord({"name": "api-node-boats", "path": "/repos/api-node-boats"})

        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "any(source_repo_name IN $source_repo_names": MockResult(
                    records=[
                        {
                            "app_name": "portal-react-platform-adb",
                            "project": "default",
                            "namespace": "adb",
                            "source_path": "helm-charts/portal-react-platform",
                        }
                    ]
                ),
                "MATCH (app:ArgoCDApplicationSet)": MockResult(records=[]),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                    records=[]
                ),
            }
        )

        result = trace_deployment_chain(db, "api-node-boats")

        assert result["argocd_applications"] == []

    def test_trace_deployment_chain_filters_provisioning_repo_to_service_relevant_terraform(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "platform_context_graph.mcp.tools.handlers.ecosystem.repository_queries.get_repository_context",
            lambda *_args, **_kwargs: {
                "repository": {
                    "id": "repository:r_boats123",
                    "name": "api-node-boats",
                    "path": "/repos/api-node-boats",
                },
                "coverage": None,
                "platforms": [],
                "deploys_from": [],
                "discovers_config_in": [],
                "provisioned_by": [
                    {
                        "id": "repository:r_tf123",
                        "name": "terraform-stack-node10",
                        "relationship_type": "PROVISIONED_BY",
                    }
                ],
                "provisions_dependencies_for": [],
                "deployment_chain": [],
                "environments": [],
                "limitations": [],
            },
        )
        repo_record = MockRecord({"name": "api-node-boats", "path": "/repos/api-node-boats"})

        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "MATCH (app:ArgoCDApplication)": MockResult(records=[]),
                "MATCH (app:ArgoCDApplicationSet)": MockResult(records=[]),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                    records=[]
                ),
                "WHERE toLower(coalesce(tf.name, '')) CONTAINS token": MockResult(
                    records=[
                        {
                            "name": "aws_route53_record.api_node_boats",
                            "resource_type": "aws_route53_record",
                            "file": "shared/resources.tf",
                            "repository": "terraform-stack-node10",
                        },
                        {
                            "name": "aws_codedeploy_deployment_group.api_node_boats",
                            "resource_type": "aws_codedeploy_deployment_group",
                            "file": "shared/ecs.tf",
                            "repository": "terraform-stack-node10",
                        }
                    ]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                    records=[
                        {
                            "name": "aws_route53_record.api_node_forex",
                            "resource_type": "aws_route53_record",
                            "file": "shared/resources.tf",
                            "repository": "terraform-stack-node10",
                        }
                    ]
                ),
                "WHERE toLower(coalesce(mod.name, '')) CONTAINS token": MockResult(
                    records=[
                        {
                            "name": "api_node_boats",
                            "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                            "version": "~> 3.0",
                            "deployment_name": "api-node-boats",
                            "repo_name": "api-node-boats",
                            "create_deploy": "true",
                            "cluster_name": "node10",
                            "zone_id": "Z123456",
                            "deploy_entry_point": "api-node-boats.js",
                            "repository": "terraform-stack-node10",
                        },
                        {
                            "name": "api_node_boats_batch",
                            "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                            "version": "~> 3.0",
                            "deployment_name": "api-node-boats-batch",
                            "repo_name": "api-node-boats",
                            "create_deploy": "false",
                            "cluster_name": "node10",
                            "zone_id": "Z123456",
                            "deploy_entry_point": "api-node-boats-batch.js",
                            "repository": "terraform-stack-node10",
                        }
                    ]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                    records=[
                        {
                            "name": "api_node_forex",
                            "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                            "version": "~> 3.0",
                            "repository": "terraform-stack-node10",
                        }
                    ]
                ),
                "MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(tg:TerragruntConfig)": MockResult(
                    records=[
                        {
                            "name": "terragrunt",
                            "terraform_source": "git::ssh://git@github.com/platformcontext/terraform-platform-modules.git//ecs/service?ref=v1.2.3",
                            "file": "terragrunt.hcl",
                            "repository": "terraform-stack-node10",
                            "source_repository": "terraform-platform-modules",
                        }
                    ]
                ),
            }
        )

        result = trace_deployment_chain(db, "api-node-boats")

        assert result["terraform_resources"] == [
            {
                "name": "aws_route53_record.api_node_boats",
                "resource_type": "aws_route53_record",
                "file": "shared/resources.tf",
                "repository": "terraform-stack-node10",
            },
            {
                "name": "aws_codedeploy_deployment_group.api_node_boats",
                "resource_type": "aws_codedeploy_deployment_group",
                "file": "shared/ecs.tf",
                "repository": "terraform-stack-node10",
            }
        ]
        assert result["terraform_modules"] == [
            {
                "name": "api_node_boats",
                "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                "version": "~> 3.0",
                "deployment_name": "api-node-boats",
                "repo_name": "api-node-boats",
                "create_deploy": "true",
                "cluster_name": "node10",
                "zone_id": "Z123456",
                "deploy_entry_point": "api-node-boats.js",
                "repository": "terraform-stack-node10",
            },
            {
                "name": "api_node_boats_batch",
                "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                "version": "~> 3.0",
                "deployment_name": "api-node-boats-batch",
                "repo_name": "api-node-boats",
                "create_deploy": "false",
                "cluster_name": "node10",
                "zone_id": "Z123456",
                "deploy_entry_point": "api-node-boats-batch.js",
                "repository": "terraform-stack-node10",
            }
        ]
        assert result["terragrunt_configs"] == [
            {
                "name": "terragrunt",
                "terraform_source": "git::ssh://git@github.com/platformcontext/terraform-platform-modules.git//ecs/service?ref=v1.2.3",
                "file": "terragrunt.hcl",
                "repository": "terraform-stack-node10",
                "source_repository": "terraform-platform-modules",
            }
        ]
        assert result["provisioning_source_chains"] == [
            {
                "repository": "terraform-stack-node10",
                "terraform_modules": [
                    {
                        "name": "api_node_boats",
                        "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                        "version": "~> 3.0",
                        "source_repository": None,
                    },
                    {
                        "name": "api_node_boats_batch",
                        "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                        "version": "~> 3.0",
                        "source_repository": None,
                    }
                ],
                "terragrunt_configs": [
                    {
                        "name": "terragrunt",
                        "terraform_source": "git::ssh://git@github.com/platformcontext/terraform-platform-modules.git//ecs/service?ref=v1.2.3",
                        "file": "terragrunt.hcl",
                        "source_repository": "terraform-platform-modules",
                    }
                ],
            }
        ]
        assert result["deployment_overview"]["network_signals"] == {
            "terraform": [
                {
                    "name": "aws_route53_record.api_node_boats",
                    "resource_type": "aws_route53_record",
                    "repository": "terraform-stack-node10",
                    "file": "shared/resources.tf",
                },
                {
                    "name": "aws_codedeploy_deployment_group.api_node_boats",
                    "resource_type": "aws_codedeploy_deployment_group",
                    "repository": "terraform-stack-node10",
                    "file": "shared/ecs.tf",
                }
            ]
        }
        assert result["deployment_overview"]["provisioning_source_chains"] == [
            {
                "repository": "terraform-stack-node10",
                "terraform_modules": [
                    {
                        "name": "api_node_boats",
                        "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                        "version": "~> 3.0",
                        "source_repository": None,
                    },
                    {
                        "name": "api_node_boats_batch",
                        "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                        "version": "~> 3.0",
                        "source_repository": None,
                    }
                ],
                "terragrunt_configs": [
                    {
                        "name": "terragrunt",
                        "terraform_source": "git::ssh://git@github.com/platformcontext/terraform-platform-modules.git//ecs/service?ref=v1.2.3",
                        "file": "terragrunt.hcl",
                        "source_repository": "terraform-platform-modules",
                    }
                ],
            }
        ]
        assert result["deployment_overview"]["service_variants"] == [
            {
                "name": "api_node_boats",
                "repository": "terraform-stack-node10",
                "module_source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                "version": "~> 3.0",
                "deployment_name": "api-node-boats",
                "repo_name": "api-node-boats",
                "create_deploy": True,
                "cluster_name": "node10",
                "zone_id": "Z123456",
                "entry_point": "api-node-boats.js",
            },
            {
                "name": "api_node_boats_batch",
                "repository": "terraform-stack-node10",
                "module_source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                "version": "~> 3.0",
                "deployment_name": "api-node-boats-batch",
                "repo_name": "api-node-boats",
                "create_deploy": False,
                "cluster_name": "node10",
                "zone_id": "Z123456",
                "entry_point": "api-node-boats-batch.js",
            },
        ]
        assert result["deployment_overview"]["deployment_controllers"] == [
            "codedeploy",
            "terraform",
        ]
