"""Compose-backed smoke test for the external ``collector-git`` Go runtime."""

from __future__ import annotations

import json
import os
import time

import pytest

pytestmark = pytest.mark.e2e

httpx = pytest.importorskip("httpx")
psycopg = pytest.importorskip("psycopg")

_BASE_URL_ENV = "PCG_E2E_COLLECTOR_BASE_URL"
_POSTGRES_DSN_ENV = "PCG_E2E_POSTGRES_DSN"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    """Return an HTTP client for the live collector admin surface."""

    base_url = os.getenv(_BASE_URL_ENV)
    if not base_url:
        pytest.skip(f"{_BASE_URL_ENV} is required for collector runtime e2e runs")

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as live_client:
        yield live_client


@pytest.fixture(scope="module")
def connection() -> psycopg.Connection:
    """Return a live Postgres connection for the smoke assertions."""

    dsn = os.getenv(_POSTGRES_DSN_ENV)
    if not dsn:
        pytest.skip(f"{_POSTGRES_DSN_ENV} is required for collector runtime e2e runs")

    with psycopg.connect(dsn) as conn:
        yield conn


def _get_json(client: httpx.Client, path: str) -> dict[str, object]:
    """Return one decoded JSON response."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _count(connection: psycopg.Connection, query: str) -> int:
    """Return one integer count from Postgres."""

    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()
    return int(row[0] if row else 0)


def _fact_kind_counts(connection: psycopg.Connection) -> dict[str, int]:
    """Return fact counts grouped by fact kind."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT fact_kind, COUNT(*) AS count
            FROM fact_records
            GROUP BY fact_kind
            """
        )
        rows = cursor.fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _poll_for_collector_activity(
    client: httpx.Client,
    connection: psycopg.Connection,
    *,
    timeout_seconds: int,
) -> dict[str, object]:
    """Poll until the collector has committed one durable generation."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, object] = {}
    while time.monotonic() < deadline:
        latest_status = _get_json(client, "/admin/status?format=json")
        if (
            _count(connection, "SELECT COUNT(*) FROM ingestion_scopes") >= 1
            and _count(connection, "SELECT COUNT(*) FROM scope_generations") >= 1
            and _count(connection, "SELECT COUNT(*) FROM fact_records") >= 4
            and _count(connection, "SELECT COUNT(*) FROM fact_work_items") >= 1
        ):
            return latest_status
        time.sleep(1.0)

    pytest.fail(
        "collector-git did not materialize durable runtime activity before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )


def test_collector_git_runtime_smoke(
    client: httpx.Client,
    connection: psycopg.Connection,
) -> None:
    """Exercise the external Go collector against compose-backed infrastructure."""

    health_response = client.get("/healthz")
    health_response.raise_for_status()
    assert "collector-git" in health_response.text

    ready_response = client.get("/readyz")
    ready_response.raise_for_status()

    status_payload = _poll_for_collector_activity(
        client,
        connection,
        timeout_seconds=int(os.getenv(_TIMEOUT_SECONDS_ENV, "90")),
    )

    assert str((status_payload.get("health") or {}).get("state") or "") in {
        "progressing",
        "healthy",
    }
    assert sum((status_payload.get("scopes") or {}).values()) >= 1
    assert sum((status_payload.get("generations") or {}).values()) >= 1
    assert int((status_payload.get("queue") or {}).get("outstanding") or 0) >= 1

    stages = list(status_payload.get("stages") or [])
    assert any(str(stage.get("stage") or "") == "projector" for stage in stages)

    fact_kind_counts = _fact_kind_counts(connection)
    assert fact_kind_counts.get("repository", 0) >= 1
    assert fact_kind_counts.get("file", 0) >= 1
    assert fact_kind_counts.get("content", 0) >= 1
    assert fact_kind_counts.get("content_entity", 0) >= 1
    assert fact_kind_counts.get("shared_followup", 0) >= 1

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT payload->>'name'
            FROM fact_records
            WHERE fact_kind = 'repository'
            ORDER BY observed_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    assert row is not None
    assert str(row[0]) == "proof-repo"
