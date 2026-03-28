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
            "get_file_content",
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
            "story": [
                "Structured repository story.",
                "Traffic enters through api-node-boats.qa.bgrp.io and deploys via GitOps.",
            ],
            "story_sections": [
                {
                    "id": "internet",
                    "title": "Internet",
                    "summary": "Traffic enters through api-node-boats.qa.bgrp.io.",
                },
                {
                    "id": "deployment",
                    "title": "Deployment",
                    "summary": "GitOps deploys onto EKS.",
                },
            ],
            "drilldowns": {"repo_context": {"repo_id": "repository:r_api_node_boats"}},
            "limitations": ["finalization_incomplete"],
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
            "limitations": ["finalization_incomplete"],
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
            "limitations": ["finalization_incomplete"],
            "coverage": {"completeness_state": "partial"},
        }
    )
    server.get_file_content_tool = MagicMock(
        side_effect=lambda **kwargs: {
            "available": True,
            "repo_id": kwargs["repo_id"],
            "relative_path": kwargs["relative_path"],
            "content": "def process_payment():\n    return True\n",
            "line_count": 2,
            "language": "python",
            "artifact_type": "python",
            "template_dialect": None,
            "iac_relevant": False,
            "source_backend": "workspace",
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


def _assert_story_contract(result: dict[str, object], case: dict[str, object]) -> None:
    assert result["story"], case["prompt"]
    assert result["story_sections"], case["prompt"]
    assert result["drilldowns"], case["prompt"]
    assert isinstance(result["limitations"], list), case["prompt"]
    for section in result["story_sections"]:
        assert section["id"], case["prompt"]
        assert section["title"], case["prompt"]
        assert section["summary"], case["prompt"]
    expected_section_ids = set(case.get("expected_story_section_ids", []))
    if expected_section_ids:
        section_ids = {section["id"] for section in result["story_sections"]}
        assert expected_section_ids.issubset(section_ids), case["prompt"]
    coverage = result.get("coverage")
    if isinstance(coverage, dict) and coverage.get("completeness_state") == "partial":
        assert result["limitations"], case["prompt"]


async def _assert_search_round_trip(
    server: MCPServer, result: dict[str, object]
) -> None:
    ranked = result["results"]["ranked_results"]
    assert ranked, "search should yield at least one drill-down candidate"
    first_result = ranked[0]
    drilldown = await server.handle_tool_call(
        "get_file_content",
        {
            "repo_id": first_result["repo_id"],
            "relative_path": first_result["relative_path"],
        },
    )
    assert drilldown["available"] is True
    assert drilldown["repo_id"] == first_result["repo_id"]
    assert drilldown["relative_path"] == first_result["relative_path"]
    assert "local_path" not in drilldown


def test_story_prompt_suite_routes_through_structured_story_surfaces() -> None:
    server = _make_server()

    async def run_cases() -> None:
        for case in STORY_PROMPT_CASES:
            result = await server.handle_tool_call(
                case["mcp"]["tool_name"],
                case["mcp"]["args"],
            )
            _assert_story_contract(result, case)

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
            if case.get("round_trip"):
                await _assert_search_round_trip(server, result)

    asyncio.run(run_cases())
