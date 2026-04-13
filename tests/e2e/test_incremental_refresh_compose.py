"""Compose-backed smoke test for incremental refresh generation replacement."""

from __future__ import annotations

import os
from typing import Any

import pytest

import incremental_refresh_compose_support as support

pytestmark = pytest.mark.e2e

httpx = pytest.importorskip("httpx")
psycopg = pytest.importorskip("psycopg")

_BASE_URL_ENV = "PCG_E2E_INCREMENTAL_REFRESH_BASE_URL"
_POSTGRES_DSN_ENV = "PCG_E2E_POSTGRES_DSN"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"

_SCOPE_ID = "scope-incremental-refresh"
_GENERATION_A_ID = "generation-incremental-refresh-a"
_GENERATION_B_ID = "generation-incremental-refresh-b"
_UNCHANGED_GENERATION_ID = "generation-incremental-refresh-unchanged"
_GRAPH_RECORD_ID = "incremental-refresh-proof-repo"
_CONTENT_PATH = "README.md"
_INITIAL_CONTENT_BODY = "# Platform Context Graph"
_CHANGED_CONTENT_BODY = "# Platform Context Graph, refreshed"
_CHANGED_FRESHNESS_HINT = "changed rerun snapshot"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    """Return an HTTP client for the live projector admin surface."""

    base_url = os.getenv(_BASE_URL_ENV)
    if not base_url:
        pytest.skip(f"{_BASE_URL_ENV} is required for incremental refresh e2e runs")

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as live_client:
        yield live_client


@pytest.fixture(scope="module")
def connection() -> psycopg.Connection[Any]:
    """Return a live Postgres connection for the smoke assertions."""

    dsn = os.getenv(_POSTGRES_DSN_ENV)
    if not dsn:
        pytest.skip(f"{_POSTGRES_DSN_ENV} is required for incremental refresh e2e runs")

    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        yield conn


def test_incremental_refresh_compose(
    client: httpx.Client,
    connection: psycopg.Connection[Any],
) -> None:
    """Prove initial projection, unchanged stability, and changed replacement."""

    timeout_seconds = int(os.getenv(_TIMEOUT_SECONDS_ENV, "120"))

    support.seed_scope_generation(
        connection,
        scope_id=_SCOPE_ID,
        generation_id=_GENERATION_A_ID,
        active_generation_id=_GENERATION_A_ID,
        generation_label="A",
        graph_record_id=_GRAPH_RECORD_ID,
        freshness_hint="initial active generation",
        generation_status="active",
        include_fact_record=True,
        include_work_item=True,
        content_path=_CONTENT_PATH,
        content_body_value=_INITIAL_CONTENT_BODY,
        content_digest="initial-content-digest",
    )

    health_response = client.get("/healthz")
    health_response.raise_for_status()
    assert "projector" in health_response.text

    ready_response = client.get("/readyz")
    ready_response.raise_for_status()

    support.wait_for_projection_state(
        client,
        connection,
        scope_id=_SCOPE_ID,
        active_generation_id=_GENERATION_A_ID,
        repo_id=_GRAPH_RECORD_ID,
        relative_path=_CONTENT_PATH,
        expected_content_body=_INITIAL_CONTENT_BODY,
        timeout_seconds=timeout_seconds,
    )

    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM ingestion_scopes
        WHERE scope_id = %s
          AND active_generation_id = %s
        """,
            (_SCOPE_ID, _GENERATION_A_ID),
        )
        == 1
    )
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM scope_generations
        WHERE scope_id = %s
          AND status = 'active'
        """,
            (_SCOPE_ID,),
        )
        == 1
    )
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM fact_work_items
        WHERE scope_id = %s
          AND stage = 'projector'
        """,
            (_SCOPE_ID,),
        )
        == 1
    )
    assert (
        support.content_body(connection, _GRAPH_RECORD_ID, _CONTENT_PATH)
        == _INITIAL_CONTENT_BODY
    )

    support.seed_scope_generation(
        connection,
        scope_id=_SCOPE_ID,
        generation_id=_UNCHANGED_GENERATION_ID,
        active_generation_id=_GENERATION_A_ID,
        generation_label="unchanged",
        graph_record_id=_GRAPH_RECORD_ID,
        freshness_hint="unchanged rerun snapshot",
        generation_status="pending",
        include_fact_record=False,
    )

    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM ingestion_scopes
        WHERE scope_id = %s
          AND active_generation_id = %s
        """,
            (_SCOPE_ID, _GENERATION_A_ID),
        )
        == 1
    )
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM scope_generations
        WHERE scope_id = %s
          AND status = 'active'
        """,
            (_SCOPE_ID,),
        )
        == 1
    )
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM fact_work_items
        WHERE scope_id = %s
          AND stage = 'projector'
        """,
            (_SCOPE_ID,),
        )
        == 1
    )

    support.seed_scope_generation(
        connection,
        scope_id=_SCOPE_ID,
        generation_id=_GENERATION_B_ID,
        active_generation_id=_GENERATION_A_ID,
        generation_label="B",
        graph_record_id=_GRAPH_RECORD_ID,
        freshness_hint=_CHANGED_FRESHNESS_HINT,
        generation_status="pending",
        include_fact_record=True,
        include_work_item=True,
        content_path=_CONTENT_PATH,
        content_body_value=_CHANGED_CONTENT_BODY,
        content_digest="changed-content-digest",
    )

    support.wait_for_retrying_work_item(
        client,
        connection,
        scope_id=_SCOPE_ID,
        generation_id=_GENERATION_B_ID,
        timeout_seconds=timeout_seconds,
    )

    status_payload = support.wait_for_projection_state(
        client,
        connection,
        scope_id=_SCOPE_ID,
        active_generation_id=_GENERATION_B_ID,
        superseded_generation_id=_GENERATION_A_ID,
        repo_id=_GRAPH_RECORD_ID,
        relative_path=_CONTENT_PATH,
        expected_content_body=_CHANGED_CONTENT_BODY,
        timeout_seconds=timeout_seconds,
        minimum_projector_succeeded=2,
    )

    assert str((status_payload.get("health") or {}).get("state") or "") in {
        "progressing",
        "healthy",
    }
    assert int((status_payload.get("queue") or {}).get("outstanding") or 0) == 0
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM scope_generations
        WHERE generation_id = %s
          AND status = 'superseded'
        """,
            (_GENERATION_A_ID,),
        )
        == 1
    )
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM scope_generations
        WHERE generation_id = %s
          AND status = 'active'
        """,
            (_GENERATION_B_ID,),
        )
        == 1
    )
    assert (
        support.count(
            connection,
            """
        SELECT COUNT(*)
        FROM ingestion_scopes
        WHERE scope_id = %s
          AND status = 'active'
          AND active_generation_id = %s
        """,
            (_SCOPE_ID, _GENERATION_B_ID),
        )
        == 1
    )
    assert (
        support.content_body(connection, _GRAPH_RECORD_ID, _CONTENT_PATH)
        == _CHANGED_CONTENT_BODY
    )
