from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")
from starlette.testclient import TestClient


def _make_client(*, query_services: object) -> TestClient:
    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: query_services)
    )


def test_investigation_route_uses_investigation_query_service() -> None:
    calls: list[dict[str, object]] = []

    def investigate_service(database: object, **kwargs: object) -> dict[str, object]:
        calls.append({"database": database, **kwargs})
        return {
            "summary": ["dual deployment detected"],
            "framework_summary": {
                "frameworks": ["nextjs"],
                "react": None,
                "nextjs": {
                    "module_count": 1,
                    "page_count": 1,
                    "layout_count": 0,
                    "route_count": 0,
                    "metadata_module_count": 0,
                    "route_handler_module_count": 0,
                    "client_runtime_count": 1,
                    "server_runtime_count": 0,
                    "route_verbs": [],
                    "sample_modules": [],
                },
            },
            "repositories_considered": [],
            "repositories_with_evidence": [],
            "evidence_families_found": ["gitops_config", "iac_infrastructure"],
            "coverage_summary": {
                "searched_repository_count": 3,
                "repositories_with_evidence_count": 2,
                "searched_evidence_families": ["gitops_config", "iac_infrastructure"],
                "found_evidence_families": ["gitops_config", "iac_infrastructure"],
                "missing_evidence_families": [],
                "deployment_mode": "multi_plane",
                "deployment_planes": [
                    {
                        "name": "gitops_controller_plane",
                        "evidence_families": ["gitops_config"],
                    },
                    {
                        "name": "iac_infrastructure_plane",
                        "evidence_families": ["iac_infrastructure"],
                    },
                ],
                "graph_completeness": "partial",
                "content_completeness": "partial",
            },
            "investigation_findings": [],
            "limitations": [],
            "recommended_next_steps": [],
            "recommended_next_calls": [],
        }

    services = SimpleNamespace(
        database=object(),
        investigation=SimpleNamespace(investigate_service=investigate_service),
    )

    with _make_client(query_services=services) as client:
        response = client.get(
            "/api/v0/investigations/services/api-node-boats"
            "?environment=bg-qa&intent=deployment&question=Explain%20the%20deployment%20flow."
        )

    assert response.status_code == 200
    assert response.json()["coverage_summary"]["deployment_mode"] == "multi_plane"
    assert calls == [
        {
            "database": services.database,
            "service_name": "api-node-boats",
            "environment": "bg-qa",
            "intent": "deployment",
            "question": "Explain the deployment flow.",
        }
    ]


def test_investigation_response_exposes_operator_coverage_fields() -> None:
    services = SimpleNamespace(
        database=object(),
        investigation=SimpleNamespace(
            investigate_service=lambda *_args, **_kwargs: {
                "summary": ["dual deployment detected"],
                "framework_summary": {
                    "frameworks": ["nextjs"],
                    "react": None,
                    "nextjs": {
                        "module_count": 1,
                        "page_count": 1,
                        "layout_count": 0,
                        "route_count": 0,
                        "metadata_module_count": 0,
                        "route_handler_module_count": 0,
                        "client_runtime_count": 1,
                        "server_runtime_count": 0,
                        "route_verbs": [],
                        "sample_modules": [],
                    },
                },
                "repositories_considered": [
                    {
                        "repo_id": "repository:r_app",
                        "repo_name": "api-node-boats",
                        "reason": "primary_service_repository",
                        "evidence_families": ["service_runtime"],
                    }
                ],
                "repositories_with_evidence": [
                    {
                        "repo_id": "repository:r_tf",
                        "repo_name": "terraform-stack-node10",
                        "reason": "oidc_role_subject",
                        "evidence_families": ["iac_infrastructure"],
                    }
                ],
                "evidence_families_found": ["service_runtime", "iac_infrastructure"],
                "coverage_summary": {
                    "searched_repository_count": 2,
                    "repositories_with_evidence_count": 1,
                    "searched_evidence_families": [
                        "service_runtime",
                        "iac_infrastructure",
                    ],
                    "found_evidence_families": [
                        "service_runtime",
                        "iac_infrastructure",
                    ],
                    "missing_evidence_families": [],
                    "deployment_mode": "single_plane",
                    "deployment_planes": [
                        {
                            "name": "iac_infrastructure_plane",
                            "evidence_families": ["iac_infrastructure"],
                        }
                    ],
                    "graph_completeness": "partial",
                    "content_completeness": "partial",
                },
                "investigation_findings": [],
                "limitations": [],
                "recommended_next_steps": [],
                "recommended_next_calls": [
                    {
                        "tool": "get_repo_story",
                        "reason": "related_deployment_repository",
                        "args": {"repo_id": "repository:r_tf"},
                    }
                ],
            }
        ),
    )

    with _make_client(query_services=services) as client:
        response = client.get("/api/v0/investigations/services/api-node-boats")

    payload = response.json()
    assert response.status_code == 200
    assert "repositories_considered" in payload
    assert "evidence_families_found" in payload
    assert payload["framework_summary"]["nextjs"]["page_count"] == 1
    assert "recommended_next_calls" in payload
