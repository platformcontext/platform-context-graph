"""Compose-backed smoke test for the external ``reducer`` Go runtime."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.e2e

httpx = pytest.importorskip("httpx")
psycopg = pytest.importorskip("psycopg")

_BASE_URL_ENV = "PCG_E2E_REDUCER_BASE_URL"
_POSTGRES_DSN_ENV = "PCG_E2E_POSTGRES_DSN"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    """Return an HTTP client for the live reducer admin surface."""

    base_url = os.getenv(_BASE_URL_ENV)
    if not base_url:
        pytest.skip(f"{_BASE_URL_ENV} is required for reducer runtime e2e runs")

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0) as live_client:
        yield live_client


@pytest.fixture(scope="module")
def connection() -> psycopg.Connection:
    """Return a live Postgres connection for the smoke assertions."""

    dsn = os.getenv(_POSTGRES_DSN_ENV)
    if not dsn:
        pytest.skip(f"{_POSTGRES_DSN_ENV} is required for reducer runtime e2e runs")

    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
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


def _seed_reducer_work_item(connection: psycopg.Connection) -> dict[str, str]:
    """Insert one workload-identity reducer item and its required parents."""

    scope_id = f"scope-{uuid.uuid4().hex[:12]}"
    generation_id = f"generation-{uuid.uuid4().hex[:12]}"
    intent_id = f"reducer_{uuid.uuid4().hex[:12]}"
    observed_at = datetime.now(timezone.utc)
    payload = {
        "entity_key": "repo:proof-repo",
        "fact_id": intent_id,
        "reason": "shared follow-up",
        "source_system": "git",
    }

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_scopes (
                scope_id, scope_kind, source_system, source_key,
                parent_scope_id, collector_kind, partition_key,
                observed_at, ingested_at, status, active_generation_id, payload
            ) VALUES (
                %s, 'repository', 'git', %s,
                NULL, 'git', %s,
                %s, %s, 'completed', NULL, %s::jsonb
            )
            """,
            (
                scope_id,
                intent_id,
                scope_id,
                observed_at,
                observed_at,
                json.dumps({"repo_id": "proof-repo"}),
            ),
        )
        cursor.execute(
            """
            INSERT INTO scope_generations (
                generation_id, scope_id, trigger_kind, freshness_hint,
                observed_at, ingested_at, status, activated_at, superseded_at, payload
            ) VALUES (
                %s, %s, 'manual', NULL,
                %s, %s, 'completed', %s, NULL, %s::jsonb
            )
            """,
            (
                generation_id,
                scope_id,
                observed_at,
                observed_at,
                observed_at,
                json.dumps({"repo_id": "proof-repo"}),
            ),
        )
        cursor.execute(
            """
            INSERT INTO fact_work_items (
                work_item_id, scope_id, generation_id, stage, domain, status,
                attempt_count, lease_owner, claim_until, visible_at, last_attempt_at,
                next_attempt_at, failure_class, failure_message, failure_details,
                payload, created_at, updated_at
            ) VALUES (
                %s, %s, %s, 'reducer', 'workload_identity', 'pending',
                0, NULL, NULL, %s, NULL,
                NULL, NULL, NULL, NULL,
                %s::jsonb, %s, %s
            )
            """,
            (
                intent_id,
                scope_id,
                generation_id,
                observed_at,
                json.dumps(payload),
                observed_at,
                observed_at,
            ),
        )

    return {
        "scope_id": scope_id,
        "generation_id": generation_id,
        "intent_id": intent_id,
        "fact_id": intent_id,
    }


def _poll_for_drain(
    client: httpx.Client,
    connection: psycopg.Connection,
    *,
    timeout_seconds: int,
) -> dict[str, object]:
    """Poll until the reducer drains the seeded queue item."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, object] = {}
    while time.monotonic() < deadline:
        latest_status = _get_json(client, "/admin/status?format=json")
        if (
            _count(connection, "SELECT COUNT(*) FROM fact_work_items WHERE status = 'succeeded'") >= 1
            and _count(connection, "SELECT COUNT(*) FROM fact_records WHERE fact_kind = 'reducer_workload_identity'") >= 1
            and int((latest_status.get("queue") or {}).get("outstanding") or 0) == 0
        ):
            return latest_status
        time.sleep(1.0)

    pytest.fail(
        "reducer did not drain the seeded queue item before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )


def test_reducer_runtime_smoke(
    client: httpx.Client,
    connection: psycopg.Connection,
) -> None:
    """Exercise the external Go reducer against compose-backed infrastructure."""

    seeded = _seed_reducer_work_item(connection)

    health_response = client.get("/healthz")
    health_response.raise_for_status()
    assert "reducer" in health_response.text

    ready_response = client.get("/readyz")
    ready_response.raise_for_status()

    status_payload = _poll_for_drain(
        client,
        connection,
        timeout_seconds=int(os.getenv(_TIMEOUT_SECONDS_ENV, "90")),
    )

    assert str((status_payload.get("health") or {}).get("state") or "") == "healthy"
    assert sum((status_payload.get("scopes") or {}).values()) >= 1
    assert sum((status_payload.get("generations") or {}).values()) >= 1
    assert int((status_payload.get("queue") or {}).get("outstanding") or 0) == 0

    stages = list(status_payload.get("stages") or [])
    reducer_stage = next(
        (stage for stage in stages if str(stage.get("stage") or "") == "reducer"),
        None,
    )
    assert reducer_stage is not None
    assert int(reducer_stage.get("succeeded") or 0) >= 1

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, payload->>'fact_id'
            FROM fact_work_items
            WHERE work_item_id = %s
            """,
            (seeded["intent_id"],),
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == "succeeded"
    assert str(row[1] or "") == seeded["intent_id"]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT payload->>'canonical_id'
            FROM fact_records
            WHERE fact_kind = 'reducer_workload_identity'
            ORDER BY observed_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    assert row is not None
    assert str(row[0] or "").startswith("canonical:workload_identity:")
