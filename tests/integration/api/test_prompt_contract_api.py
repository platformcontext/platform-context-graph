from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from tests.integration.prompt_contract_cases import (
    PROGRAMMING_PROMPT_CASES,
    STORY_PROMPT_CASES,
)

pytest.importorskip("httpx")
from starlette.testclient import TestClient


def _make_client(*, query_services: object) -> TestClient:
    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: query_services)
    )


def _repository_story(*_args, **_kwargs) -> dict[str, object]:
    return {
        "subject": {
            "id": "repository:r_api_node_boats",
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
        "deployment_overview": {"internet_entrypoints": ["api-node-boats.qa.bgrp.io"]},
        "evidence": [{"source": "hostnames", "detail": "api-node-boats.qa.bgrp.io"}],
        "limitations": ["finalization_incomplete"],
        "coverage": {"completeness_state": "partial"},
        "drilldowns": {"repo_context": {"repo_id": "repository:r_api_node_boats"}},
    }


def _workload_story(*_args, **_kwargs) -> dict[str, object]:
    return {
        "subject": {
            "id": "workload:api-node-boats",
            "type": "workload",
            "kind": "service",
            "name": "api-node-boats",
        },
        "story": ["Structured workload story."],
        "story_sections": [
            {
                "id": "runtime",
                "title": "Runtime",
                "summary": "qa and prod instances are known.",
            }
        ],
        "deployment_overview": {
            "instances": [{"id": "workload-instance:api-node-boats:qa"}]
        },
        "evidence": [{"source": "instances", "detail": "qa"}],
        "limitations": [],
        "coverage": None,
        "drilldowns": {"workload_context": {"workload_id": "workload:api-node-boats"}},
    }


def _service_story(*_args, **_kwargs) -> dict[str, object]:
    payload = _workload_story()
    payload["story"] = ["Structured service story."]
    payload["requested_as"] = "service"
    payload["drilldowns"] = {
        "service_context": {"workload_id": "workload:api-node-boats"}
    }
    return payload


def _search_code(*_args, **_kwargs) -> dict[str, object]:
    return {
        "ranked_results": [
            {"repo_id": "repository:r_ab12cd34", "relative_path": "src/payments.py"}
        ]
    }


def _relationships(*_args, **_kwargs) -> dict[str, object]:
    return {
        "results": [
            {"repo_id": "repository:r_ab12cd34", "relative_path": "src/payments.py"}
        ]
    }


def _dead_code(*_args, **_kwargs) -> dict[str, object]:
    return {
        "potentially_unused_functions": [
            {
                "function_name": "legacy_helper",
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/legacy.py",
            }
        ]
    }


def _complexity(*_args, **kwargs) -> dict[str, object]:
    if kwargs.get("mode") == "function":
        return {"function_name": "process_payment", "complexity": 12}
    return {
        "functions": [
            {
                "name": "process_payment",
                "complexity": 12,
                "repo_id": "repository:r_ab12cd34",
            }
        ]
    }


def _get_file_content(*_args, **kwargs) -> dict[str, object]:
    return {
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


def _call_case(client: TestClient, case: dict[str, object]):
    request = case["http"]
    method = request["method"].lower()
    if method == "get":
        return client.get(request["path"], params=request.get("params"))
    return client.post(request["path"], json=request.get("json"))


def _assert_story_contract(
    body: dict[str, object],
    case: dict[str, object],
) -> None:
    assert body["story"], case["prompt"]
    assert body["story_sections"], case["prompt"]
    assert body["drilldowns"], case["prompt"]
    assert isinstance(body["limitations"], list), case["prompt"]
    for section in body["story_sections"]:
        assert section["id"], case["prompt"]
        assert section["title"], case["prompt"]
        assert section["summary"], case["prompt"]
    expected_section_ids = set(case.get("expected_story_section_ids", []))
    if expected_section_ids:
        section_ids = {section["id"] for section in body["story_sections"]}
        assert expected_section_ids.issubset(section_ids), case["prompt"]
    coverage = body.get("coverage")
    if isinstance(coverage, dict) and coverage.get("completeness_state") == "partial":
        assert body["limitations"], case["prompt"]


def _assert_search_round_trip(client: TestClient, body: dict[str, object]) -> None:
    ranked = body["ranked_results"]
    assert ranked, "search should yield at least one drill-down candidate"
    first_result = ranked[0]
    response = client.post(
        "/api/v0/content/files/read",
        json={
            "repo_id": first_result["repo_id"],
            "relative_path": first_result["relative_path"],
        },
    )
    assert response.status_code == 200
    content = response.json()
    assert content["repo_id"] == first_result["repo_id"]
    assert content["relative_path"] == first_result["relative_path"]
    assert "local_path" not in content


def test_story_prompt_suite_routes_through_structured_story_http_surfaces() -> None:
    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(get_repository_story=_repository_story),
        context=SimpleNamespace(
            get_workload_story=_workload_story,
            get_service_story=_service_story,
        ),
    )

    with _make_client(query_services=services) as client:
        for case in STORY_PROMPT_CASES:
            response = _call_case(client, case)
            assert response.status_code == 200, case["prompt"]
            body = response.json()
            _assert_story_contract(body, case)


def test_programming_prompt_suite_routes_through_http_code_surfaces() -> None:
    services = SimpleNamespace(
        database=object(),
        content=SimpleNamespace(get_file_content=_get_file_content),
        code=SimpleNamespace(
            search_code=_search_code,
            get_code_relationships=_relationships,
            find_dead_code=_dead_code,
            get_complexity=_complexity,
        ),
    )

    with _make_client(query_services=services) as client:
        for case in PROGRAMMING_PROMPT_CASES:
            response = _call_case(client, case)
            assert response.status_code == 200, case["prompt"]
            body = response.json()
            if case["kind"] == "search":
                assert body["ranked_results"], case["prompt"]
                if case.get("round_trip"):
                    _assert_search_round_trip(client, body)
                continue
            if case["kind"] == "dead_code":
                assert body["potentially_unused_functions"], case["prompt"]
                continue
            if case["kind"].startswith("complexity"):
                assert (
                    body.get("functions") or body.get("complexity") is not None
                ), case["prompt"]
                continue
            assert body["results"], case["prompt"]
