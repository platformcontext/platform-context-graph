from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")
from starlette.testclient import TestClient

WORKLOAD_CONTEXT = {
    "workload": {
        "id": "workload:payments-api",
        "type": "workload",
        "kind": "service",
        "name": "payments-api",
    },
    "instance": {
        "id": "workload-instance:payments-api:prod",
        "type": "workload_instance",
        "kind": "service",
        "name": "payments-api",
        "environment": "prod",
        "workload_id": "workload:payments-api",
    },
    "repositories": [
        {
            "id": "repository:r_ab12cd34",
            "type": "repository",
            "name": "payments-api",
            "repo_slug": "platformcontext/payments-api",
            "remote_url": "https://github.com/platformcontext/payments-api",
            "has_remote": True,
        }
    ],
    "images": [],
    "instances": [],
    "k8s_resources": [],
    "cloud_resources": [],
    "shared_resources": [],
    "dependencies": [],
    "entrypoints": [],
    "evidence": [],
}

SERVICE_CONTEXT = {
    **WORKLOAD_CONTEXT,
    "requested_as": "service",
}

STORY_RESPONSE = {
    "subject": WORKLOAD_CONTEXT["workload"],
    "story": ["payments-api serves card-present transactions in prod."],
    "story_sections": [
        {
            "id": "runtime",
            "title": "Runtime",
            "summary": "prod instance runs in EKS.",
            "items": [WORKLOAD_CONTEXT["instance"]],
        }
    ],
    "deployment_overview": {"instances": [WORKLOAD_CONTEXT["instance"]]},
    "deployment_fact_summary": {
        "adapter": "cloudformation",
        "mapping_mode": "iac",
        "overall_confidence": "high",
        "evidence_sources": ["delivery_path", "platform"],
        "high_confidence_fact_types": [
            "PROVISIONED_BY_IAC",
            "RUNS_ON_PLATFORM",
        ],
        "medium_confidence_fact_types": [],
        "limitations": [],
    },
    "deployment_facts": [
        {
            "fact_type": "PROVISIONED_BY_IAC",
            "adapter": "cloudformation",
            "value": "cloudformation",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": "cloudformation_eks",
                }
            ],
        }
    ],
    "evidence": [],
    "limitations": [],
    "coverage": None,
    "drilldowns": {"workload_context": {"workload_id": "workload:payments-api"}},
}

ENTITY_CONTEXT = {
    "entity": WORKLOAD_CONTEXT["workload"],
    **WORKLOAD_CONTEXT,
}

RESOLVE_ENTITY_RESPONSE = {
    "matches": [
        {
            "ref": WORKLOAD_CONTEXT["workload"],
            "score": 0.98,
        }
    ]
}


def _make_query_services() -> object:
    return SimpleNamespace(
        database=object(),
        entity_resolution=SimpleNamespace(
            resolve_entity=lambda *_args, **_kwargs: RESOLVE_ENTITY_RESPONSE
        ),
        context=SimpleNamespace(
            get_entity_context=lambda *_args, **_kwargs: ENTITY_CONTEXT,
            get_workload_context=lambda *_args, **_kwargs: WORKLOAD_CONTEXT,
            get_service_context=lambda *_args, **_kwargs: SERVICE_CONTEXT,
            get_workload_story=lambda *_args, **_kwargs: STORY_RESPONSE,
            get_service_story=lambda *_args, **_kwargs: {
                **STORY_RESPONSE,
                "requested_as": "service",
            },
        ),
        impact=SimpleNamespace(
            trace_resource_to_code=lambda *_args, **_kwargs: {"paths": []},
            explain_dependency_path=lambda *_args, **_kwargs: {"path": {}},
            find_change_surface=lambda *_args, **_kwargs: {"impacted": []},
        ),
        compare=SimpleNamespace(
            compare_environments=lambda *_args, **_kwargs: {
                "changed": {"cloud_resources": []}
            }
        ),
        code=SimpleNamespace(
            search_code=lambda *_args, **_kwargs: {
                "ranked_results": [{"path": "src/payments.py"}]
            },
            get_code_relationships=lambda *_args, **_kwargs: {"results": []},
            find_dead_code=lambda *_args, **_kwargs: {
                "potentially_unused_functions": []
            },
            get_complexity=lambda *_args, **_kwargs: {"functions": []},
        ),
        infra=SimpleNamespace(
            search_infra_resources=lambda *_args, **_kwargs: {"matches": []},
            get_infra_relationships=lambda *_args, **_kwargs: {"relationships": []},
            get_ecosystem_overview=lambda *_args, **_kwargs: {"repositories": []},
        ),
        repositories=SimpleNamespace(
            list_repositories=lambda *_args, **_kwargs: {"repositories": []},
            get_repository_context=lambda *_args, **_kwargs: {
                "repository": {"name": "payments-api"}
            },
            get_repository_story=lambda *_args, **_kwargs: {
                **STORY_RESPONSE,
                "subject": {
                    "id": "repository:r_ab12cd34",
                    "type": "repository",
                    "name": "payments-api",
                },
                "drilldowns": {"repo_context": {"repo_id": "repository:r_ab12cd34"}},
            },
            get_repository_stats=lambda *_args, **_kwargs: {
                "success": True,
                "stats": {},
            },
        ),
    )


def _make_client(*, query_services: object) -> TestClient:
    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: query_services)
    )


def test_openapi_uses_typed_response_models_for_context_and_resolve_routes() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        schema = client.get("/api/v0/openapi.json").json()

    resolve_schema = schema["paths"]["/api/v0/entities/resolve"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    entity_schema = schema["paths"]["/api/v0/entities/{entity_id}/context"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    workload_schema = schema["paths"]["/api/v0/workloads/{workload_id}/context"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    service_schema = schema["paths"]["/api/v0/services/{workload_id}/context"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    workload_story_schema = schema["paths"]["/api/v0/workloads/{workload_id}/story"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    service_story_schema = schema["paths"]["/api/v0/services/{workload_id}/story"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    repository_story_schema = schema["paths"]["/api/v0/repositories/{repo_id}/story"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]

    assert resolve_schema["$ref"] == "#/components/schemas/ResolveEntityResponse"
    assert entity_schema["$ref"] == "#/components/schemas/EntityContextResponse"
    assert workload_schema["$ref"] == "#/components/schemas/WorkloadContextResponse"
    assert service_schema["$ref"] == "#/components/schemas/WorkloadContextResponse"
    assert workload_story_schema["$ref"] == "#/components/schemas/StoryResponse"
    assert service_story_schema["$ref"] == "#/components/schemas/StoryResponse"
    assert repository_story_schema["$ref"] == "#/components/schemas/StoryResponse"


def test_service_and_workload_routes_stay_aligned_for_environment_context() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        workload_response = client.get(
            "/api/v0/workloads/workload:payments-api/context?environment=prod"
        )
        service_response = client.get(
            "/api/v0/services/workload:payments-api/context?environment=prod"
        )

    assert workload_response.status_code == 200
    assert service_response.status_code == 200
    assert workload_response.json()["workload"] == service_response.json()["workload"]
    assert workload_response.json()["instance"] == service_response.json()["instance"]
    assert "requested_as" not in workload_response.json()
    assert service_response.json()["requested_as"] == "service"


def test_openapi_examples_cover_service_alias_and_code_only_workflows() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        schema = client.get("/api/v0/openapi.json").json()

    service_examples = schema["paths"]["/api/v0/services/{workload_id}/context"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]
    workload_examples = schema["paths"]["/api/v0/workloads/{workload_id}/context"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["examples"]
    resolve_examples = schema["paths"]["/api/v0/entities/resolve"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["examples"]
    code_search_examples = schema["paths"]["/api/v0/code/search"]["post"][
        "requestBody"
    ]["content"]["application/json"]["examples"]
    repo_story_examples = schema["paths"]["/api/v0/repositories/{repo_id}/story"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["examples"]

    assert service_examples["service_alias"]["value"]["requested_as"] == "service"
    assert (
        service_examples["service_alias"]["value"]["workload"]["id"]
        == "workload:payments-api"
    )
    assert (
        workload_examples["environment_context"]["value"]["instance"]["id"]
        == "workload-instance:payments-api:prod"
    )
    assert (
        resolve_examples["workload_match"]["value"]["matches"][0]["ref"]["id"]
        == "workload:payments-api"
    )
    assert code_search_examples["code_only"]["value"] == {
        "query": "process_payment",
        "repo_id": "repository:r_ab12cd34",
        "exact": False,
        "limit": 10,
    }
    assert (
        repo_story_examples["repository_story"]["value"]["subject"]["id"]
        == "repository:r_ab12cd34"
    )
    assert (
        repo_story_examples["repository_story"]["value"]["deployment_fact_summary"][
            "mapping_mode"
        ]
        == "controller"
    )
    assert (
        schema["paths"]["/api/v0/workloads/{workload_id}/story"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["examples"]["workload_story"]["value"][
            "deployment_fact_summary"
        ][
            "mapping_mode"
        ]
        == "iac"
    )


def test_openapi_examples_match_live_service_alias_response_shape() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        schema = client.get("/api/v0/openapi.json").json()
        response = client.get(
            "/api/v0/services/workload:payments-api/context?environment=prod"
        )

    assert response.status_code == 200
    documented = schema["paths"]["/api/v0/services/{workload_id}/context"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]["service_alias"]["value"]
    assert response.json() == documented


def test_openapi_story_examples_include_deployment_mapping_contract() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        schema = client.get("/api/v0/openapi.json").json()

    service_story = schema["paths"]["/api/v0/services/{workload_id}/story"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["examples"]["service_story"]["value"]

    assert service_story["deployment_fact_summary"] == {
        "adapter": "cloudformation",
        "mapping_mode": "iac",
        "overall_confidence": "high",
        "evidence_sources": ["delivery_path", "platform"],
        "high_confidence_fact_types": [
            "PROVISIONED_BY_IAC",
            "RUNS_ON_PLATFORM",
        ],
        "medium_confidence_fact_types": [],
        "limitations": [],
    }
    assert service_story["deployment_facts"][0]["fact_type"] == "PROVISIONED_BY_IAC"


def test_openapi_exposes_query_routes_without_deployment_control_endpoints() -> None:
    with _make_client(query_services=_make_query_services()) as client:
        schema = client.get("/api/v0/openapi.json").json()

    paths = schema["paths"]
    assert "/api/v0/repositories" in paths
    assert "/api/v0/repositories/{repo_id}/context" in paths
    assert "/api/v0/repositories/{repo_id}/story" in paths
    assert "/api/v0/repositories/{repo_id}/stats" in paths
    assert "/api/v0/workloads/{workload_id}/story" in paths
    assert "/api/v0/services/{workload_id}/story" in paths
    assert "/api/v0/index" not in paths
    assert "/api/v0/watch" not in paths
    assert "/api/v0/jobs" not in paths
    assert "/api/v0/jobs/{job_id}" not in paths
