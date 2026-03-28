from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from platform_context_graph.mcp import MCPServer
from platform_context_graph.mcp.tool_registry import TOOLS

from tests.integration.prompt_contract_cases import (
    PROGRAMMING_PROMPT_CASES,
    STORY_PROMPT_CASES,
)


def _make_server() -> MCPServer:
    server = MCPServer.__new__(MCPServer)
    server.tools = {
        name: TOOLS[name]
        for name in {
            "get_repo_story",
            "get_workload_story",
            "get_service_story",
            "find_code",
            "analyze_code_relationships",
            "calculate_cyclomatic_complexity",
            "find_most_complex_functions",
            "find_dead_code",
        }
    }
    server.get_repo_story_tool = MagicMock(
        side_effect=lambda **kwargs: {
            "subject": {
                "id": kwargs.get("repo_id", "repository:r_api_node_boats"),
                "type": "repository",
                "name": "api-node-boats",
            },
            "story": ["Structured repository story."],
            "story_sections": [
                {
                    "id": "deployment",
                    "title": "Deployment",
                    "summary": "GitOps deploys onto EKS.",
                }
            ],
            "drilldowns": {"repo_context": {"repo_id": "repository:r_api_node_boats"}},
            "limitations": [],
            "coverage": {"completeness_state": "partial"},
        }
    )
    server.get_workload_story_tool = MagicMock(
        side_effect=lambda **kwargs: {
            "subject": {
                "id": kwargs.get("workload_id", "workload:api-node-boats"),
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "story": ["Structured workload story."],
            "story_sections": [
                {
                    "id": "runtime",
                    "title": "Runtime",
                    "summary": "Workload instances span qa and prod.",
                }
            ],
            "drilldowns": {
                "workload_context": {"workload_id": "workload:api-node-boats"}
            },
            "limitations": [],
            "coverage": {"completeness_state": "partial"},
        }
    )
    server.get_service_story_tool = MagicMock(
        side_effect=lambda **kwargs: {
            "subject": {
                "id": kwargs.get("workload_id", "workload:api-node-boats"),
                "type": "workload",
                "kind": "service",
                "name": "api-node-boats",
            },
            "story": ["Structured service story."],
            "story_sections": [
                {
                    "id": "runtime",
                    "title": "Runtime",
                    "summary": (
                        "qa instance runs in EKS."
                        if kwargs.get("environment") == "qa"
                        else "Service runs in EKS."
                    ),
                }
            ],
            "drilldowns": {
                "service_context": {"workload_id": "workload:api-node-boats"}
            },
            "requested_as": "service",
            "limitations": [],
            "coverage": {"completeness_state": "partial"},
        }
    )
    server.find_code_tool = MagicMock(
        return_value={
            "success": True,
            "results": {
                "ranked_results": [
                    {
                        "repo_id": "repository:r_payments_api",
                        "relative_path": "src/payments.py",
                    }
                ]
            },
        }
    )
    server.analyze_code_relationships_tool = MagicMock(
        return_value={
            "success": True,
            "results": {
                "items": [
                    {
                        "repo_id": "repository:r_payments_api",
                        "relative_path": "src/payments.py",
                    }
                ]
            },
        }
    )
    server.calculate_cyclomatic_complexity_tool = MagicMock(
        return_value={
            "success": True,
            "results": {"function_name": "process_payment", "complexity": 12},
        }
    )
    server.find_most_complex_functions_tool = MagicMock(
        return_value={
            "success": True,
            "results": {"functions": [{"name": "process_payment", "complexity": 12}]},
        }
    )
    server.find_dead_code_tool = MagicMock(
        return_value={
            "success": True,
            "results": {
                "potentially_unused_functions": [
                    {
                        "function_name": "legacy_helper",
                        "repo_id": "repository:r_payments_api",
                        "relative_path": "src/legacy.py",
                    }
                ]
            },
        }
    )
    return server


def _assert_programming_result(
    case: dict[str, object], result: dict[str, object]
) -> None:
    kind = case["kind"]
    assert result.get("success") is True, case["prompt"]
    payload = result.get("results")
    assert isinstance(payload, dict), case["prompt"]
    if kind == "search":
        ranked = payload.get("ranked_results")
        assert isinstance(ranked, list) and ranked, case["prompt"]
        assert ranked[0]["repo_id"].startswith("repository:"), case["prompt"]
        assert ranked[0]["relative_path"], case["prompt"]
        return
    if kind == "relationships":
        items = payload.get("items")
        assert isinstance(items, list) and items, case["prompt"]
        assert items[0]["repo_id"].startswith("repository:"), case["prompt"]
        assert items[0]["relative_path"], case["prompt"]
        return
    if kind == "complexity_function":
        assert payload["function_name"] == "process_payment", case["prompt"]
        assert payload["complexity"] == 12, case["prompt"]
        return
    if kind == "complexity_top":
        functions = payload.get("functions")
        assert isinstance(functions, list) and functions, case["prompt"]
        assert functions[0]["complexity"] == 12, case["prompt"]
        return
    if kind == "dead_code":
        dead_code = payload.get("potentially_unused_functions")
        assert isinstance(dead_code, list) and dead_code, case["prompt"]
        assert dead_code[0]["repo_id"].startswith("repository:"), case["prompt"]
        assert dead_code[0]["relative_path"], case["prompt"]
        return
    raise AssertionError(f"Unhandled programming case kind: {kind}")


def test_story_prompt_suite_routes_through_structured_story_surfaces() -> None:
    server = _make_server()

    async def run_cases() -> None:
        for case in STORY_PROMPT_CASES:
            result = await server.handle_tool_call(
                case["mcp"]["tool_name"],
                case["mcp"]["args"],
            )
            assert result["story"], case["prompt"]
            assert result["story_sections"], case["prompt"]
            assert result["drilldowns"], case["prompt"]

    asyncio.run(run_cases())


def test_programming_prompt_suite_routes_through_code_contract_surfaces() -> None:
    server = _make_server()

    async def run_cases() -> None:
        for case in PROGRAMMING_PROMPT_CASES:
            result = await server.handle_tool_call(
                case["mcp"]["tool_name"],
                case["mcp"]["args"],
            )
            _assert_programming_result(case, result)

    asyncio.run(run_cases())
