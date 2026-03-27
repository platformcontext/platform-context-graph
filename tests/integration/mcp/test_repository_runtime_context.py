from __future__ import annotations

from unittest.mock import patch

from platform_context_graph.mcp import MCPServer


def test_get_repo_summary_tool_surfaces_platforms_and_limitations() -> None:
    server = MCPServer.__new__(MCPServer)
    server.db_manager = object()

    with patch(
        "platform_context_graph.mcp.query_tools.ecosystem.get_repo_summary",
        return_value={
            "name": "api-node-boats",
            "story": [
                "Public entrypoints: api-node-boats.qa.bgrp.io.",
                "GitHub Actions deploy from helm-charts onto EKS.",
            ],
            "platforms": [
                {"id": "platform:ecs:aws:cluster/node10", "kind": "ecs"}
            ],
            "delivery_workflows": {
                "github_actions": {
                    "commands": [
                        {
                            "command": "deploy-eks",
                            "workflow": "node-api-deploy-eks.yml",
                        }
                    ]
                }
            },
            "delivery_paths": [
                {"path_kind": "gitops", "delivery_mode": "eks_gitops"}
            ],
            "api_surface": {"docs_routes": ["/_specs"], "api_versions": ["v3"]},
            "hostnames": [{"hostname": "api-node-boats.qa.bgrp.io"}],
            "limitations": ["dns_unknown", "entrypoint_unknown"],
        },
    ) as mock_summary:
        result = server.get_repo_summary_tool(repo_name="api-node-boats")

    mock_summary.assert_called_once_with(server.db_manager, "api-node-boats")
    assert result["story"] == [
        "Public entrypoints: api-node-boats.qa.bgrp.io.",
        "GitHub Actions deploy from helm-charts onto EKS.",
    ]
    assert result["platforms"] == [
        {"id": "platform:ecs:aws:cluster/node10", "kind": "ecs"}
    ]
    assert result["delivery_workflows"]["github_actions"]["commands"] == [
        {"command": "deploy-eks", "workflow": "node-api-deploy-eks.yml"}
    ]
    assert result["delivery_paths"] == [
        {"path_kind": "gitops", "delivery_mode": "eks_gitops"}
    ]
    assert result["api_surface"]["docs_routes"] == ["/_specs"]
    assert result["hostnames"][0]["hostname"] == "api-node-boats.qa.bgrp.io"
    assert result["limitations"] == ["dns_unknown", "entrypoint_unknown"]


def test_trace_deployment_chain_tool_surfaces_runtime_context_and_limitations() -> None:
    server = MCPServer.__new__(MCPServer)
    server.db_manager = object()

    with patch(
        "platform_context_graph.mcp.query_tools.ecosystem.trace_deployment_chain",
        return_value={
            "repository": {"name": "api-node-boats"},
            "story": [
                "Public entrypoints: api-node-boats.qa.bgrp.io.",
                "GitHub Actions deploy through terraform-stack-node10 onto ECS.",
            ],
            "platforms": [{"id": "platform:ecs:aws:cluster/node10", "kind": "ecs"}],
            "deploys_from": [{"name": "helm-charts"}],
            "delivery_workflows": {
                "jenkins": [
                    {
                        "relative_path": "Jenkinsfile",
                        "pipeline_calls": ["pipelinePM2"],
                    }
                ]
            },
            "delivery_paths": [
                {"path_kind": "direct", "controller": "jenkins"}
            ],
            "api_surface": {"api_versions": ["v3"]},
            "hostnames": [{"hostname": "api-node-boats.qa.bgrp.io"}],
            "limitations": ["dns_unknown", "entrypoint_unknown"],
        },
    ) as mock_trace:
        result = server.trace_deployment_chain_tool(service_name="api-node-boats")

    mock_trace.assert_called_once_with(server.db_manager, "api-node-boats")
    assert result["story"] == [
        "Public entrypoints: api-node-boats.qa.bgrp.io.",
        "GitHub Actions deploy through terraform-stack-node10 onto ECS.",
    ]
    assert result["platforms"] == [
        {"id": "platform:ecs:aws:cluster/node10", "kind": "ecs"}
    ]
    assert result["delivery_workflows"]["jenkins"] == [
        {"relative_path": "Jenkinsfile", "pipeline_calls": ["pipelinePM2"]}
    ]
    assert result["delivery_paths"] == [
        {"path_kind": "direct", "controller": "jenkins"}
    ]
    assert result["api_surface"]["api_versions"] == ["v3"]
    assert result["hostnames"][0]["hostname"] == "api-node-boats.qa.bgrp.io"
    assert result["limitations"] == ["dns_unknown", "entrypoint_unknown"]
