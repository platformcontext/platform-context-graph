"""Focused deployment-story overview tests for trace handlers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from platform_context_graph.mcp.tools.handlers.ecosystem import (
    trace_deployment_chain,
)


class MockResult:
    """Mock Neo4j query results for focused deployment-story tests."""

    def __init__(
        self,
        records: list[dict[str, Any]] | None = None,
        single_record: dict[str, Any] | None = None,
    ) -> None:
        self._records = records or []
        self._single_record = single_record

    def single(self) -> dict[str, Any] | None:
        """Return the single-record result when one was configured."""

        return self._single_record

    def data(self) -> list[dict[str, Any]]:
        """Return the full result set."""

        return self._records


def make_mock_db(query_results: dict[str, MockResult]) -> MagicMock:
    """Create a mock db manager that matches queries by substring."""

    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query: str, **_kwargs: Any) -> MockResult:
        for substring, result in query_results.items():
            if substring in query:
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_trace_deployment_chain_exposes_gitops_and_documentation_overviews(
    monkeypatch,
) -> None:
    """Deployment traces should expose GitOps, documentation, and support views."""

    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem_support.repository_queries.get_repository_context",
        lambda *_args, **_kwargs: {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "repo_slug": "boatsgroup/api-node-boats",
            },
            "deploys_from": [
                {
                    "id": "repository:r_helm",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                }
            ],
            "discovers_config_in": [],
            "provisioned_by": [],
            "platforms": [{"kind": "eks"}],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
            "controller_driven_paths": [],
            "deployment_artifacts": {
                "config_paths": [
                    {
                        "path": "argocd/api-node-boats/base/values.yaml",
                        "source_repo": "helm-charts",
                    }
                ]
            },
            "hostnames": [{"hostname": "api-node-boats.qa.bgrp.io"}],
            "api_surface": {"docs_routes": ["/_specs"]},
            "consumer_repositories": [
                {
                    "repository": "api-node-boattrader",
                    "repo_id": "repository:r_consumer",
                    "evidence_kinds": ["repository_reference"],
                    "sample_paths": ["api-node-boattrader.ts"],
                }
            ],
            "summary": {},
            "coverage": None,
            "limitations": [],
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem_support.collect_documentation_evidence",
        lambda *_args, **_kwargs: {
            "graph_context": [],
            "file_content": [
                {
                    "repo_id": "repository:r_api_node_boats",
                    "relative_path": "README.md",
                    "source_backend": "postgres",
                    "title": "API Node Boats",
                    "summary": "Support hints",
                }
            ],
            "entity_content": [],
            "content_search": [],
        },
    )

    db = make_mock_db({})
    session = db.get_driver.return_value.session.return_value

    def repo_only_run(query, **kwargs):
        """Return a repository match only for the trace seed lookup."""

        del kwargs
        if "RETURN r.id as id, r.name as name" in query:
            return MockResult(
                single_record={
                    "id": "repository:r_api_node_boats",
                    "name": "api-node-boats",
                }
            )
        return MockResult(records=[])

    session.run = repo_only_run

    result = trace_deployment_chain(db, "api-node-boats")

    assert result["gitops_overview"]["owner"]["delivery_controllers"] == [
        "github_actions"
    ]
    assert result["documentation_overview"]["key_artifacts"][0]["relative_path"] == (
        "argocd/api-node-boats/base/values.yaml"
    )
    assert result["support_overview"]["investigation_paths"][0]["topic"] == (
        "request_failures"
    )
    assert result["support_overview"]["dependency_hotspots"] == []
    assert result["support_overview"]["consumer_repositories"][0]["repository"] == (
        "api-node-boattrader"
    )


def test_trace_deployment_chain_ranks_gitops_artifacts_ahead_of_readme(
    monkeypatch,
) -> None:
    """Trace output should prioritize deployment artifacts over generic docs."""

    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem_support.repository_queries.get_repository_context",
        lambda *_args, **_kwargs: {
            "repository": {
                "id": "repository:r_api_node_boats",
                "name": "api-node-boats",
                "repo_slug": "boatsgroup/api-node-boats",
            },
            "deploys_from": [
                {
                    "id": "repository:r_helm",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                }
            ],
            "discovers_config_in": [],
            "provisioned_by": [],
            "platforms": [{"kind": "eks"}],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "github_actions",
                    "delivery_mode": "eks_gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
            "controller_driven_paths": [],
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
                    }
                ],
            },
            "hostnames": [{"hostname": "api-node-boats.qa.bgrp.io"}],
            "api_surface": {
                "spec_files": [
                    {
                        "relative_path": "specs/openapi.yaml",
                        "discovered_from": "api-node-boats.ts",
                    }
                ]
            },
            "consumer_repositories": [],
            "summary": {},
            "coverage": None,
            "limitations": [],
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.mcp.tools.handlers.ecosystem_support.collect_documentation_evidence",
        lambda *_args, **_kwargs: {
            "graph_context": [],
            "file_content": [
                {
                    "repo_id": "repository:r_api_node_boats",
                    "relative_path": "README.md",
                    "source_backend": "postgres",
                    "title": "API Node Boats",
                    "summary": "Support hints",
                }
            ],
            "entity_content": [],
            "content_search": [],
        },
    )

    db = make_mock_db({})
    session = db.get_driver.return_value.session.return_value

    def repo_only_run(query, **kwargs):
        """Return a repository match only for the trace seed lookup."""

        del kwargs
        if "RETURN r.id as id, r.name as name" in query:
            return MockResult(
                single_record={
                    "id": "repository:r_api_node_boats",
                    "name": "api-node-boats",
                }
            )
        return MockResult(records=[])

    session.run = repo_only_run

    result = trace_deployment_chain(db, "api-node-boats")

    artifact_paths = [
        artifact["relative_path"]
        for artifact in result["support_overview"]["key_artifacts"][:4]
    ]
    assert artifact_paths == [
        "argocd/api-node-boats/overlays/bg-qa/values.yaml",
        "argocd/api-node-boats/base/values.yaml",
        "argocd/api-node-boats/base/xirsarole.yaml",
        "specs/openapi.yaml",
    ]
