"""Integration tests for the HTTP content routes."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")
from starlette.testclient import TestClient


def _make_query_services() -> object:
    """Build a query-service stub with the content module attached."""

    return SimpleNamespace(
        database=object(),
        content=SimpleNamespace(
            get_file_content=lambda *_args, **_kwargs: {
                "available": True,
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/payments.py",
                "content": "print('payments')\n",
                "line_count": 1,
                "language": "python",
                "artifact_type": "jinja_yaml",
                "template_dialect": "jinja",
                "iac_relevant": True,
                "source_backend": "workspace",
            },
            get_file_lines=lambda *_args, **_kwargs: {
                "available": True,
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/payments.py",
                "start_line": 1,
                "end_line": 1,
                "lines": [{"line_number": 1, "content": "print('payments')"}],
                "artifact_type": "jinja_yaml",
                "template_dialect": "jinja",
                "iac_relevant": True,
                "source_backend": "workspace",
            },
            get_entity_content=lambda *_args, **_kwargs: {
                "available": True,
                "entity_id": "content-entity:e_ab12cd34ef56",
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/payments.py",
                "entity_type": "Function",
                "entity_name": "process_payment",
                "start_line": 1,
                "end_line": 3,
                "content": "def process_payment():\n    return True\n",
                "language": "python",
                "artifact_type": "jinja_yaml",
                "template_dialect": "jinja",
                "iac_relevant": True,
                "source_backend": "workspace",
            },
            search_file_content=lambda *_args, **_kwargs: {
                "pattern": "payments",
                "matches": [
                    {
                        "repo_id": "repository:r_ab12cd34",
                        "relative_path": "src/payments.py",
                        "language": "python",
                        "artifact_type": "jinja_yaml",
                        "template_dialect": "jinja",
                        "iac_relevant": True,
                        "snippet": "print('payments')",
                        "source_backend": "postgres",
                    }
                ],
            },
            search_entity_content=lambda *_args, **_kwargs: {
                "pattern": "process_payment",
                "matches": [
                    {
                        "entity_id": "content-entity:e_ab12cd34ef56",
                        "repo_id": "repository:r_ab12cd34",
                        "relative_path": "src/payments.py",
                        "entity_type": "Function",
                        "entity_name": "process_payment",
                        "language": "python",
                        "artifact_type": "jinja_yaml",
                        "template_dialect": "jinja",
                        "iac_relevant": True,
                        "snippet": "def process_payment",
                        "source_backend": "postgres",
                    }
                ],
            },
        ),
    )


def _make_client() -> TestClient:
    """Create a test client for the HTTP API."""

    api_app = importlib.import_module("platform_context_graph.api.app")
    return TestClient(
        api_app.create_app(query_services_dependency=lambda: _make_query_services())
    )


def test_content_routes_return_portable_repo_and_entity_identifiers() -> None:
    """Expose content operations without server-local filesystem identifiers."""

    with _make_client() as client:
        file_response = client.post(
            "/api/v0/content/files/read",
            json={
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/payments.py",
            },
        )
        lines_response = client.post(
            "/api/v0/content/files/lines",
            json={
                "repo_id": "repository:r_ab12cd34",
                "relative_path": "src/payments.py",
                "start_line": 1,
                "end_line": 1,
            },
        )
        entity_response = client.post(
            "/api/v0/content/entities/read",
            json={"entity_id": "content-entity:e_ab12cd34ef56"},
        )

    assert file_response.status_code == 200
    assert lines_response.status_code == 200
    assert entity_response.status_code == 200
    assert file_response.json()["repo_id"] == "repository:r_ab12cd34"
    assert file_response.json()["relative_path"] == "src/payments.py"
    assert file_response.json()["artifact_type"] == "jinja_yaml"
    assert file_response.json()["template_dialect"] == "jinja"
    assert file_response.json()["iac_relevant"] is True
    assert "local_path" not in file_response.json()
    assert lines_response.json()["lines"][0]["line_number"] == 1
    assert lines_response.json()["artifact_type"] == "jinja_yaml"
    assert entity_response.json()["entity_id"] == "content-entity:e_ab12cd34ef56"
    assert entity_response.json()["artifact_type"] == "jinja_yaml"


def test_content_search_routes_accept_metadata_filters() -> None:
    """File and entity search routes should accept metadata filter arguments."""

    with _make_client() as client:
        file_response = client.post(
            "/api/v0/content/files/search",
            json={
                "pattern": "payments",
                "artifact_types": ["jinja_yaml"],
                "template_dialects": ["jinja"],
                "iac_relevant": True,
            },
        )
        entity_response = client.post(
            "/api/v0/content/entities/search",
            json={
                "pattern": "process_payment",
                "artifact_types": ["jinja_yaml"],
                "template_dialects": ["jinja"],
                "iac_relevant": True,
            },
        )

    assert file_response.status_code == 200
    assert entity_response.status_code == 200
    assert file_response.json()["matches"][0]["artifact_type"] == "jinja_yaml"
    assert entity_response.json()["matches"][0]["template_dialect"] == "jinja"


def test_content_search_routes_are_exposed_in_openapi() -> None:
    """Document the file and entity content search surfaces."""

    with _make_client() as client:
        schema = client.get("/api/v0/openapi.json").json()

    assert "/api/v0/content/files/read" in schema["paths"]
    assert "/api/v0/content/files/lines" in schema["paths"]
    assert "/api/v0/content/entities/read" in schema["paths"]
    assert "/api/v0/content/files/search" in schema["paths"]
    assert "/api/v0/content/entities/search" in schema["paths"]
