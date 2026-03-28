from __future__ import annotations

import asyncio
import importlib
import json

import pytest

from platform_context_graph.mcp import MCPServer

pytest.importorskip("httpx")
from starlette.testclient import TestClient

from tests.integration.conftest import skip_no_neo4j

pytestmark = [pytest.mark.slow, skip_no_neo4j]


STORY_PROMPTS = [
    {
        "prompt": "Tell me the end-to-end deployment story for argocd_comprehensive.",
        "surface": "mcp",
        "repo_name": "argocd_comprehensive",
    },
    {
        "prompt": "Show me the Internet-to-cloud-to-code story for helm_argocd_platform.",
        "surface": "http",
        "repo_name": "helm_argocd_platform",
    },
    {
        "prompt": "Summarize kubernetes_comprehensive from public surface to deployment evidence.",
        "surface": "mcp",
        "repo_name": "kubernetes_comprehensive",
    },
    {
        "prompt": "What infrastructure and deployment clues exist in terraform_comprehensive?",
        "surface": "http",
        "repo_name": "terraform_comprehensive",
    },
    {
        "prompt": "Explain how ansible_jenkins_automation is delivered.",
        "surface": "mcp",
        "repo_name": "ansible_jenkins_automation",
    },
]

PROGRAMMING_PROMPTS = [
    {
        "prompt": "Where is greet defined in python_comprehensive?",
        "surface": "mcp",
        "tool_name": "find_code",
        "args": {"query": "greet"},
        "repo_id_name": "python_comprehensive",
        "kind": "search",
    },
    {
        "prompt": "Where is Config defined in python_comprehensive?",
        "surface": "http",
        "path": "/api/v0/code/search",
        "json": {"query": "Config", "repo_id_name": "python_comprehensive"},
        "kind": "search",
    },
    {
        "prompt": "Where is Employee defined in java_comprehensive?",
        "surface": "http",
        "path": "/api/v0/code/search",
        "json": {"query": "Employee", "repo_id_name": "java_comprehensive"},
        "kind": "search",
    },
    {
        "prompt": "Show the class hierarchy for Employee.",
        "surface": "mcp",
        "tool_name": "analyze_code_relationships",
        "args": {"query_type": "class_hierarchy", "target": "Employee"},
        "expected_fragment": "Employee",
    },
    {
        "prompt": "Show the most complex functions in python_comprehensive.",
        "surface": "http",
        "path": "/api/v0/code/complexity",
        "json": {
            "mode": "top",
            "limit": 5,
            "repo_id_name": "python_comprehensive",
        },
        "kind": "complexity",
    },
]


def _assert_story_payload(payload: dict[str, object], prompt: str) -> None:
    assert payload["story"], prompt
    assert payload["story_sections"], prompt
    assert payload["drilldowns"], prompt
    assert isinstance(payload["limitations"], list), prompt
    for section in payload["story_sections"]:
        assert section["id"], prompt
        assert section["title"], prompt
        assert section["summary"], prompt
    coverage = payload.get("coverage")
    if isinstance(coverage, dict) and coverage.get("completeness_state") == "partial":
        assert payload["limitations"], prompt


def _assert_search_round_trip_http(
    live_http_client: TestClient, result: dict[str, object], prompt: str
) -> None:
    ranked = result["ranked_results"]
    assert ranked, prompt
    first_result = ranked[0]
    response = live_http_client.post(
        "/api/v0/content/files/read",
        json={
            "repo_id": first_result["repo_id"],
            "relative_path": first_result["relative_path"],
        },
    )
    assert response.status_code == 200, prompt
    payload = response.json()
    assert payload["repo_id"] == first_result["repo_id"], prompt
    assert payload["relative_path"] == first_result["relative_path"], prompt
    assert "local_path" not in payload, prompt


async def _assert_search_round_trip_mcp(
    live_mcp_server: MCPServer, result: dict[str, object], prompt: str
) -> None:
    ranked = result["ranked_results"]
    assert ranked, prompt
    first_result = ranked[0]
    payload = await live_mcp_server.handle_tool_call(
        "get_file_content",
        {
            "repo_id": first_result["repo_id"],
            "relative_path": first_result["relative_path"],
        },
    )
    assert payload["available"] is True, prompt
    assert payload["repo_id"] == first_result["repo_id"], prompt
    assert payload["relative_path"] == first_result["relative_path"], prompt
    assert "local_path" not in payload, prompt


def _repository_id(server: MCPServer, repo_name: str) -> str:
    driver = server.db_manager.get_driver()
    with driver.session() as session:
        record = session.run(
            "MATCH (r:Repository {name: $repo_name}) RETURN r.id as id LIMIT 1",
            repo_name=repo_name,
        ).single()
    assert record is not None, f"Repository '{repo_name}' should exist in seeded graph"
    return record["id"]


@pytest.fixture(scope="module")
def live_mcp_server() -> MCPServer:
    """Create a real MCP server bound to the live Neo4j test graph."""

    return MCPServer()


@pytest.fixture(scope="module")
def live_http_client() -> TestClient:
    """Create a real HTTP client bound to the live Neo4j test graph."""

    api_app = importlib.import_module("platform_context_graph.api.app")
    with TestClient(api_app.create_app()) as client:
        yield client


def test_story_and_programming_prompt_journeys_against_live_graph(
    seeded_e2e_graph: None,
    live_mcp_server: MCPServer,
    live_http_client: TestClient,
) -> None:
    """Exercise flagship story and programming prompts against the live graph."""

    del seeded_e2e_graph

    for case in STORY_PROMPTS:
        if case["surface"] == "mcp":
            result = asyncio.run(
                live_mcp_server.handle_tool_call(
                    "get_repo_story",
                    {"repo_id": case["repo_name"]},
                )
            )
            payload = result
        else:
            repo_id = _repository_id(live_mcp_server, case["repo_name"])
            response = live_http_client.get(f"/api/v0/repositories/{repo_id}/story")
            assert response.status_code == 200, case["prompt"]
            payload = response.json()

        assert payload["subject"]["type"] == "repository", case["prompt"]
        _assert_story_payload(payload, case["prompt"])
        assert "local_path" not in json.dumps(payload), case["prompt"]

    for case in PROGRAMMING_PROMPTS:
        if case["surface"] == "mcp":
            args = dict(case["args"])
            repo_name = case.get("repo_id_name")
            if repo_name is not None:
                args["repo_id"] = _repository_id(live_mcp_server, repo_name)
            result = asyncio.run(
                live_mcp_server.handle_tool_call(case["tool_name"], args)
            )
            assert result.get("success") is True, case["prompt"]
            payload = result.get("results", result)
        else:
            body = dict(case["json"])
            repo_name = body.pop("repo_id_name", None)
            if repo_name is not None:
                body["repo_id"] = _repository_id(live_mcp_server, repo_name)
            response = live_http_client.post(case["path"], json=body)
            assert response.status_code == 200, case["prompt"]
            payload = response.json()

        serialized = json.dumps(payload)
        if case.get("kind") == "search":
            ranked = payload.get("ranked_results")
            assert isinstance(ranked, list) and ranked, case["prompt"]
            assert ranked[0]["repo_id"].startswith("repository:"), case["prompt"]
            assert ranked[0]["relative_path"], case["prompt"]
            if case["surface"] == "mcp":
                asyncio.run(
                    _assert_search_round_trip_mcp(
                        live_mcp_server,
                        payload,
                        case["prompt"],
                    )
                )
            else:
                _assert_search_round_trip_http(
                    live_http_client, payload, case["prompt"]
                )
            continue
        if case.get("kind") == "complexity":
            functions = (
                payload.get("functions") if isinstance(payload, dict) else payload
            )
            assert isinstance(functions, list) and functions, case["prompt"]
            continue

        assert payload, case["prompt"]
        expected_fragment = case.get("expected_fragment")
        if expected_fragment is not None:
            assert expected_fragment in serialized, case["prompt"]
