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
        "story": ["Structured repository story."],
        "story_sections": [
            {
                "id": "deployment",
                "title": "Deployment",
                "summary": "GitOps deploys onto EKS.",
            }
        ],
        "deployment_overview": {"internet_entrypoints": ["api-node-boats.qa.bgrp.io"]},
        "evidence": [{"source": "hostnames", "detail": "api-node-boats.qa.bgrp.io"}],
        "limitations": [],
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


def _call_case(client: TestClient, case: dict[str, object]):
    request = case["http"]
    method = request["method"].lower()
    if method == "get":
        return client.get(request["path"], params=request.get("params"))
    return client.post(request["path"], json=request.get("json"))


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
            assert body["story"], case["prompt"]
            assert body["story_sections"], case["prompt"]
            assert body["drilldowns"], case["prompt"]


def test_programming_prompt_suite_routes_through_http_code_surfaces() -> None:
    services = SimpleNamespace(
        database=object(),
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
