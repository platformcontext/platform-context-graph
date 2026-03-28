from __future__ import annotations

from unittest.mock import patch

from platform_context_graph.mcp import MCPServer


def test_get_repo_story_tool_surfaces_story_contract() -> None:
    server = MCPServer.__new__(MCPServer)
    server.db_manager = object()

    with patch(
        "platform_context_graph.mcp.query_tools.repository_queries.get_repository_story",
        return_value={
            "subject": {
                "id": "repository:r_api_node_boats",
                "type": "repository",
                "name": "api-node-boats",
            },
            "story": ["api-node-boats is exposed through api-node-boats.qa.bgrp.io."],
            "story_sections": [
                {
                    "id": "internet",
                    "title": "Internet",
                    "summary": "Traffic enters through api-node-boats.qa.bgrp.io.",
                }
            ],
            "deployment_overview": {"platforms": [{"kind": "eks"}]},
            "evidence": [],
            "limitations": ["dns_unknown"],
            "coverage": {"completeness_state": "partial"},
            "drilldowns": {"repo_context": {"repo_id": "repository:r_api_node_boats"}},
        },
    ) as mock_story:
        result = server.get_repo_story_tool(repo_id="api-node-boats")

    mock_story.assert_called_once_with(server.db_manager, repo_id="api-node-boats")
    assert result["subject"]["name"] == "api-node-boats"
    assert result["story_sections"][0]["id"] == "internet"


def test_workload_and_service_story_tools_route_through_context_queries() -> None:
    server = MCPServer.__new__(MCPServer)
    server.db_manager = object()

    with patch(
        "platform_context_graph.mcp.query_tools.context_queries.get_workload_story",
        return_value={"subject": {"id": "workload:payments-api"}, "story": []},
    ) as mock_workload_story, patch(
        "platform_context_graph.mcp.query_tools.context_queries.get_service_story",
        return_value={
            "subject": {"id": "workload:payments-api"},
            "story": [],
            "requested_as": "service",
        },
    ) as mock_service_story:
        workload_result = server.get_workload_story_tool(
            workload_id="payments-api",
            environment="prod",
        )
        service_result = server.get_service_story_tool(
            workload_id="payments-api",
            environment="prod",
        )

    mock_workload_story.assert_called_once_with(
        server.db_manager,
        workload_id="payments-api",
        environment="prod",
    )
    mock_service_story.assert_called_once_with(
        server.db_manager,
        workload_id="payments-api",
        environment="prod",
    )
    assert workload_result["subject"]["id"] == "workload:payments-api"
    assert service_result["requested_as"] == "service"


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
            "controller_driven_paths": [],
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
    assert result["controller_driven_paths"] == []
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
            "controller_driven_paths": [
                {
                    "controller_kind": "jenkins",
                    "automation_kind": "ansible",
                    "entry_points": ["deploy.yml"],
                }
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
    assert result["controller_driven_paths"] == [
        {
            "controller_kind": "jenkins",
            "automation_kind": "ansible",
            "entry_points": ["deploy.yml"],
        }
    ]
    assert result["api_surface"]["api_versions"] == ["v3"]
    assert result["hostnames"][0]["hostname"] == "api-node-boats.qa.bgrp.io"
    assert result["limitations"] == ["dns_unknown", "entrypoint_unknown"]
