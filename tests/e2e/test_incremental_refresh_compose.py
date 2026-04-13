"""Compose-backed smoke test for incremental refresh generation replacement."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from collections.abc import Mapping
from typing import Any

import pytest

pytestmark = pytest.mark.e2e

httpx = pytest.importorskip("httpx")
psycopg = pytest.importorskip("psycopg")

_BASE_URL_ENV = "PCG_E2E_INCREMENTAL_REFRESH_BASE_URL"
_POSTGRES_DSN_ENV = "PCG_E2E_POSTGRES_DSN"
_TIMEOUT_SECONDS_ENV = "PCG_E2E_TIMEOUT_SECONDS"

_SCOPE_ID = "scope-incremental-refresh"
_GENERATION_A_ID = "generation-incremental-refresh-a"
_GENERATION_B_ID = "generation-incremental-refresh-b"
_WORK_ITEM_ID = f"projector_{_SCOPE_ID}_{_GENERATION_B_ID}"
_GRAPH_RECORD_ID = "incremental-refresh-proof-repo"
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


def _get_json(client: httpx.Client, path: str) -> dict[str, Any]:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _count(
    connection: psycopg.Connection[Any],
    query: str,
    params: tuple[Any, ...] = (),
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    return int(row[0] if row else 0)


def _seed_scope_generation(
    connection: psycopg.Connection[Any],
    *,
    generation_id: str,
    generation_label: str,
    freshness_hint: str,
    generation_status: str,
    include_fact_record: bool,
    include_work_item: bool,
    work_item_id: str | None,
    work_item_status: str = "pending",
    work_item_visible_at: dt.datetime | None = None,
    work_item_failure_class: str | None = None,
    work_item_failure_message: str | None = None,
) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    observed = now - dt.timedelta(minutes=1)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_scopes (
                scope_id, scope_kind, source_system, source_key, parent_scope_id,
                collector_kind, partition_key, observed_at, ingested_at, status,
                active_generation_id, payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (scope_id) DO UPDATE SET
                scope_kind = EXCLUDED.scope_kind,
                source_system = EXCLUDED.source_system,
                source_key = EXCLUDED.source_key,
                parent_scope_id = EXCLUDED.parent_scope_id,
                collector_kind = EXCLUDED.collector_kind,
                partition_key = EXCLUDED.partition_key,
                observed_at = EXCLUDED.observed_at,
                ingested_at = EXCLUDED.ingested_at,
                status = EXCLUDED.status,
                active_generation_id = EXCLUDED.active_generation_id,
                payload = EXCLUDED.payload
            """,
            (
                _SCOPE_ID,
                "repository",
                "git",
                "incremental-refresh-proof-scope",
                None,
                "git",
                _SCOPE_ID,
                observed,
                now,
                "active",
                _GENERATION_A_ID,
                json.dumps({"repo_id": _GRAPH_RECORD_ID}),
            ),
        )
        cursor.execute(
            """
            INSERT INTO scope_generations (
                generation_id, scope_id, trigger_kind, freshness_hint,
                observed_at, ingested_at, status, activated_at, superseded_at, payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s::jsonb
            )
            ON CONFLICT (generation_id) DO UPDATE SET
                scope_id = EXCLUDED.scope_id,
                trigger_kind = EXCLUDED.trigger_kind,
                freshness_hint = EXCLUDED.freshness_hint,
                observed_at = EXCLUDED.observed_at,
                ingested_at = EXCLUDED.ingested_at,
                status = EXCLUDED.status,
                activated_at = EXCLUDED.activated_at,
                superseded_at = EXCLUDED.superseded_at,
                payload = EXCLUDED.payload
            """,
            (
                generation_id,
                _SCOPE_ID,
                "snapshot",
                freshness_hint,
                observed,
                now,
                generation_status,
                observed if generation_status == "active" else None,
                json.dumps({"repo_id": _GRAPH_RECORD_ID, "generation": generation_label}),
            ),
        )
        if include_fact_record:
            cursor.execute(
                """
                INSERT INTO fact_records (
                    fact_id, scope_id, generation_id, fact_kind, stable_fact_key,
                    source_system, source_fact_key, source_uri, source_record_id,
                    observed_at, ingested_at, is_tombstone, payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (fact_id) DO UPDATE SET
                    fact_kind = EXCLUDED.fact_kind,
                    stable_fact_key = EXCLUDED.stable_fact_key,
                    source_system = EXCLUDED.source_system,
                    source_fact_key = EXCLUDED.source_fact_key,
                    source_uri = EXCLUDED.source_uri,
                    source_record_id = EXCLUDED.source_record_id,
                    observed_at = EXCLUDED.observed_at,
                    ingested_at = EXCLUDED.ingested_at,
                    is_tombstone = EXCLUDED.is_tombstone,
                    payload = EXCLUDED.payload
                """,
                (
                    f"fact-{generation_id}",
                    _SCOPE_ID,
                    generation_id,
                    "repository",
                    f"repository:{_GRAPH_RECORD_ID}",
                    "git",
                    "incremental-refresh-proof-scope",
                    None,
                    None,
                    observed,
                    now,
                    False,
                    json.dumps(
                        {
                            "graph_id": _GRAPH_RECORD_ID,
                            "graph_kind": "repository",
                            "name": "incremental-refresh-proof-repo",
                        }
                    ),
                ),
            )
        if include_work_item and work_item_id is not None:
            work_item_visible_at = work_item_visible_at or now
            cursor.execute(
                """
                INSERT INTO fact_work_items (work_item_id, scope_id, generation_id, stage, domain, status, attempt_count, lease_owner, claim_until, visible_at, last_attempt_at, next_attempt_at, failure_class, failure_message, failure_details, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 1, NULL, NULL, %s, %s, %s, %s, %s, NULL, '{}'::jsonb, %s, %s)
                ON CONFLICT (work_item_id) DO UPDATE SET
                    scope_id = EXCLUDED.scope_id,
                    generation_id = EXCLUDED.generation_id,
                    stage = EXCLUDED.stage,
                    domain = EXCLUDED.domain,
                    status = EXCLUDED.status,
                    attempt_count = EXCLUDED.attempt_count,
                    lease_owner = EXCLUDED.lease_owner,
                    claim_until = EXCLUDED.claim_until,
                    visible_at = EXCLUDED.visible_at,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    next_attempt_at = EXCLUDED.next_attempt_at,
                    failure_class = EXCLUDED.failure_class,
                    failure_message = EXCLUDED.failure_message,
                    failure_details = EXCLUDED.failure_details,
                    payload = EXCLUDED.payload,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    work_item_id,
                    _SCOPE_ID,
                    generation_id,
                    "projector",
                    "source_local",
                    work_item_status,
                    work_item_visible_at,
                    work_item_visible_at,
                    work_item_visible_at,
                    work_item_failure_class,
                    work_item_failure_message,
                    now,
                    now,
                ),
            )


def _seed_initial_active_generation(connection: psycopg.Connection[Any]) -> None:
    _seed_scope_generation(connection, generation_id=_GENERATION_A_ID, generation_label="A", freshness_hint="initial active generation", generation_status="active", include_fact_record=True, include_work_item=False, work_item_id=None)


def _seed_unchanged_rerun_generation(connection: psycopg.Connection[Any]) -> None:
    _seed_scope_generation(connection, generation_id="generation-incremental-refresh-unchanged", generation_label="unchanged", freshness_hint="unchanged rerun snapshot", generation_status="pending", include_fact_record=False, include_work_item=False, work_item_id=None)


def _seed_retryable_changed_rerun_generation(connection: psycopg.Connection[Any]) -> None:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    _seed_scope_generation(
        connection,
        generation_id=_GENERATION_B_ID,
        generation_label="B",
        freshness_hint=_CHANGED_FRESHNESS_HINT,
        generation_status="pending",
        include_fact_record=True,
        include_work_item=True,
        work_item_id=_WORK_ITEM_ID,
        work_item_status="retrying",
        work_item_visible_at=now + dt.timedelta(seconds=2),
        work_item_failure_class="projection_failed",
        work_item_failure_message="projection failed once",
    )


def _wait_for_refresh(
    client: httpx.Client,
    connection: psycopg.Connection[Any],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_status = _get_json(client, "/admin/status?format=json")
        if (
            _count(
                connection,
                "SELECT COUNT(*) FROM scope_generations WHERE generation_id = %s AND status = 'superseded'",
                (_GENERATION_A_ID,),
            )
            >= 1
            and _count(
                connection,
                "SELECT COUNT(*) FROM scope_generations WHERE generation_id = %s AND status = 'active'",
                (_GENERATION_B_ID,),
            )
            >= 1
            and _count(
                connection,
                """
                SELECT COUNT(*)
                FROM ingestion_scopes
                WHERE scope_id = %s
                  AND active_generation_id = %s
                """,
                (_SCOPE_ID, _GENERATION_B_ID),
            )
            >= 1
            and _count(
                connection,
                """
                SELECT COUNT(*)
                FROM fact_work_items
                WHERE work_item_id = %s
                  AND status = 'succeeded'
                """,
                (_WORK_ITEM_ID,),
            )
            >= 1
            and int((latest_status.get("queue") or {}).get("outstanding") or 0) == 0
        ):
            stage_rows = {
                str(stage.get("stage") or ""): stage
                for stage in list(latest_status.get("stages") or [])
                if isinstance(stage, Mapping)
            }
            if int((stage_rows.get("projector") or {}).get("succeeded") or 0) >= 1:
                return latest_status
        time.sleep(1.0)

    pytest.fail(
        "incremental refresh did not converge before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )


def test_incremental_refresh_compose(
    client: httpx.Client,
    connection: psycopg.Connection[Any],
) -> None:
    _seed_initial_active_generation(connection)

    health_response = client.get("/healthz")
    health_response.raise_for_status()
    assert "projector" in health_response.text

    ready_response = client.get("/readyz")
    ready_response.raise_for_status()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT active_generation_id
            FROM ingestion_scopes
            WHERE scope_id = %s
            """,
            (_SCOPE_ID,),
        )
        initial_active_generation = cursor.fetchone()
    assert initial_active_generation is not None
    assert initial_active_generation[0] == _GENERATION_A_ID
    assert _count(
        connection,
        """
        SELECT COUNT(*)
        FROM scope_generations
        WHERE scope_id = %s
          AND status = 'active'
        """,
        (_SCOPE_ID,),
    ) == 1
    assert _count(
        connection,
        """
        SELECT COUNT(*)
        FROM fact_work_items
        WHERE scope_id = %s
          AND stage = 'projector'
        """,
        (_SCOPE_ID,),
    ) == 0

    _seed_unchanged_rerun_generation(connection)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT active_generation_id
            FROM ingestion_scopes
            WHERE scope_id = %s
            """,
            (_SCOPE_ID,),
        ); unchanged_active_generation = cursor.fetchone()
    assert unchanged_active_generation and unchanged_active_generation[0] == _GENERATION_A_ID
    assert _count(
        connection,
        """
        SELECT COUNT(*)
        FROM scope_generations
        WHERE scope_id = %s
          AND status = 'active'
        """,
        (_SCOPE_ID,),
    ) == 1
    assert _count(
        connection,
        """
        SELECT COUNT(*)
        FROM fact_work_items
        WHERE scope_id = %s
          AND stage = 'projector'
        """,
        (_SCOPE_ID,),
    ) == 0

    _seed_retryable_changed_rerun_generation(connection)

    assert _count(
        connection,
        """
        SELECT COUNT(*)
        FROM fact_work_items
        WHERE work_item_id = %s
          AND status = 'retrying'
          AND failure_class = 'projection_failed'
        """,
        (_WORK_ITEM_ID,),
    ) == 1
    assert _count(
        connection,
        """
        SELECT COUNT(*)
        FROM fact_work_items
        WHERE scope_id = %s
          AND stage = 'projector'
          AND status IN ('pending', 'retrying')
        """,
        (_SCOPE_ID,),
    ) == 1

    status_payload = _wait_for_refresh(
        client,
        connection,
        timeout_seconds=int(os.getenv(_TIMEOUT_SECONDS_ENV, "120")),
    )

    assert str((status_payload.get("health") or {}).get("state") or "") in {
        "progressing",
        "healthy",
    }
    assert int((status_payload.get("queue") or {}).get("outstanding") or 0) == 0

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, activated_at, superseded_at
            FROM scope_generations
            WHERE generation_id = %s
            """,
            (_GENERATION_A_ID,),
        )
        generation_a = cursor.fetchone()
        cursor.execute(
            """
            SELECT status, activated_at, superseded_at
            FROM scope_generations
            WHERE generation_id = %s
            """,
            (_GENERATION_B_ID,),
        )
        generation_b = cursor.fetchone()
        cursor.execute(
            """
            SELECT status, active_generation_id
            FROM ingestion_scopes
            WHERE scope_id = %s
            """,
            (_SCOPE_ID,),
        )
        scope_row = cursor.fetchone()

    assert generation_a is not None
    assert generation_a[0] == "superseded"
    assert generation_a[1] is not None
    assert generation_a[2] is not None
    assert generation_b is not None
    assert generation_b[0] == "active"
    assert generation_b[1] is not None
    assert generation_b[2] is None
    assert scope_row is not None
    assert scope_row[0] == "active"
    assert scope_row[1] == _GENERATION_B_ID
