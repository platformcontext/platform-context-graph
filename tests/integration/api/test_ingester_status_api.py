"""Integration coverage for ingester status response payloads."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_create_app_exposes_shared_projection_status_fields() -> None:
    """The ingester status route should preserve shared-write status details."""

    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    api_app = importlib.import_module("platform_context_graph.api.app")

    class _StatusModule:
        """Minimal status service exposing shared backlog and tuning fields."""

        KNOWN_INGESTERS = ("repository",)

        @staticmethod
        def get_ingester_status(_database, *, ingester="repository"):
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": ingester,
                "source_mode": "githubOrg",
                "status": "indexing",
                "active_run_id": "run-123",
                "repository_count": 200,
                "pulled_repositories": 180,
                "in_sync_repositories": 18,
                "pending_repositories": 2,
                "completed_repositories": 180,
                "failed_repositories": 0,
                "shared_projection_pending_repositories": 2,
                "shared_projection_backlog": [
                    {
                        "projection_domain": "repo_dependency",
                        "pending_intents": 2,
                        "oldest_pending_age_seconds": 33.0,
                    }
                ],
                "shared_projection_tuning": {
                    "projection_domains": [
                        "repo_dependency",
                        "workload_dependency",
                    ],
                    "include_platform": False,
                    "current_pending_intents": 2,
                    "current_oldest_pending_age_seconds": 33.0,
                    "recommended": {
                        "setting": "4x2",
                        "partition_count": 4,
                        "batch_limit": 2,
                        "round_count": 2,
                        "processed_total": 32,
                        "peak_pending_total": 32,
                        "mean_processed_per_round": 16.0,
                    },
                },
                "scan_request_state": "idle",
                "scan_request_token": None,
                "scan_requested_at": None,
                "scan_requested_by": None,
                "scan_started_at": None,
                "scan_completed_at": None,
                "scan_error_message": None,
                "updated_at": "2026-03-22T12:00:00+00:00",
            }

    app = api_app.create_app(
        query_services_dependency=lambda: SimpleNamespace(
            database=object(),
            status=_StatusModule(),
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v0/ingesters/repository")

    assert response.status_code == 200
    payload = response.json()
    assert payload["shared_projection_pending_repositories"] == 2
    assert payload["shared_projection_backlog"] == [
        {
            "projection_domain": "repo_dependency",
            "pending_intents": 2,
            "oldest_pending_age_seconds": 33.0,
        }
    ]
    assert payload["shared_projection_tuning"]["recommended"]["setting"] == "4x2"
