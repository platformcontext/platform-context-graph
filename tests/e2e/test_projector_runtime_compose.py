"""Compose-backed smoke test for the projector Go runtime."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import pytest

pytestmark = pytest.mark.e2e

httpx = pytest.importorskip("httpx")
psycopg = pytest.importorskip("psycopg")

_BASE_URL_ENV = "PCG_E2E_PROJECTOR_BASE_URL"
_POSTGRES_DSN_ENV = "PCG_E2E_POSTGRES_DSN"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    """Return an HTTP client for the live projector admin surface."""

    base_url = os.getenv(_BASE_URL_ENV)
    if not base_url:
        pytest.skip(f"{_BASE_URL_ENV} is required for projector runtime e2e runs")

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as live_client:
        yield live_client


@pytest.fixture(scope="module")
def connection() -> psycopg.Connection[Any]:
    """Return a live Postgres connection for the smoke assertions."""

    dsn = os.getenv(_POSTGRES_DSN_ENV)
    if not dsn:
        pytest.skip(f"{_POSTGRES_DSN_ENV} is required for projector runtime e2e runs")

    with psycopg.connect(dsn) as conn:
        yield conn


def _get_json(client: httpx.Client, path: str) -> dict[str, Any]:
    """Return one decoded JSON response."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _count(
    connection: psycopg.Connection[Any],
    query: str,
    params: tuple[Any, ...] = (),
) -> int:
    """Return one integer count from Postgres."""

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    return int(row[0] if row else 0)


def _stage_counts(
    connection: psycopg.Connection[Any],
) -> dict[tuple[str, str], int]:
    """Return work-item counts grouped by stage and status."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT stage, status, COUNT(*) AS count
            FROM fact_work_items
            GROUP BY stage, status
            """
        )
        rows = cursor.fetchall()
    return {(str(row[0]), str(row[1])): int(row[2]) for row in rows}


def _wait_for_projection(
    client: httpx.Client,
    connection: psycopg.Connection[Any],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Poll until the projector has consumed its work item and emitted follow-up."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_status = _get_json(client, "/admin/status?format=json")
        if (
            _count(connection, "SELECT COUNT(*) FROM ingestion_scopes") >= 1
            and _count(connection, "SELECT COUNT(*) FROM scope_generations") >= 1
            and _count(connection, "SELECT COUNT(*) FROM fact_records") >= 2
            and _count(connection, "SELECT COUNT(*) FROM fact_work_items") >= 2
            and _count(
                connection,
                """
                SELECT COUNT(*)
                FROM content_files
                WHERE repo_id = %s
                """,
                ("repository:r_projector_proof",),
            )
            >= 1
            and _count(
                connection,
                """
                SELECT COUNT(*)
                FROM content_entities
                WHERE repo_id = %s
                """,
                ("repository:r_projector_proof",),
            )
            >= 1
        ):
            stage_counts = _stage_counts(connection)
            if (
                stage_counts.get(("projector", "succeeded"), 0) >= 1
                and stage_counts.get(("reducer", "pending"), 0) >= 1
            ):
                return latest_status
        time.sleep(1.0)

    pytest.fail(
        "projector did not consume and project the seeded work before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )


def test_projector_runtime_smoke(
    client: httpx.Client,
    connection: psycopg.Connection[Any],
) -> None:
    """Exercise the external Go projector against compose-backed infrastructure."""

    health_response = client.get("/healthz")
    health_response.raise_for_status()
    assert "projector" in health_response.text

    ready_response = client.get("/readyz")
    ready_response.raise_for_status()

    status_payload = _wait_for_projection(
        client,
        connection,
        timeout_seconds=int(os.getenv(_TIMEOUT_SECONDS_ENV, "90")),
    )

    assert str((status_payload.get("health") or {}).get("state") or "") in {
        "progressing",
        "healthy",
    }
    assert int((status_payload.get("queue") or {}).get("succeeded") or 0) >= 1
    assert int((status_payload.get("queue") or {}).get("outstanding") or 0) >= 1

    stage_rows = {
        str(stage.get("stage") or ""): stage
        for stage in list(status_payload.get("stages") or [])
        if isinstance(stage, Mapping)
    }
    assert int((stage_rows.get("projector") or {}).get("succeeded") or 0) >= 1
    assert int((stage_rows.get("reducer") or {}).get("pending") or 0) >= 1

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
    assert str(row[0]) == "projector-proof-repo"

    assert (
        _count(
            connection,
            """
            SELECT COUNT(*)
            FROM content_files
            WHERE repo_id = %s
              AND relative_path = %s
            """,
            ("repository:r_projector_proof", "README.md"),
        )
        >= 1
    )
    assert (
        _count(
            connection,
            """
            SELECT COUNT(*)
            FROM content_entities
            WHERE repo_id = %s
              AND entity_name = %s
            """,
            ("repository:r_projector_proof", "public.projector_proof"),
        )
        >= 1
    )
