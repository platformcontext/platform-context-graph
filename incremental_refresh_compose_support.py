"""Shared helpers for the incremental refresh compose proof."""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any


def get_json(client: Any, path: str) -> dict[str, Any]:
    """Return the decoded JSON payload for one admin endpoint."""

    response = client.get(path)
    response.raise_for_status()
    return response.json()


def count(
    connection: Any,
    query: str,
    params: tuple[Any, ...] = (),
) -> int:
    """Return the integer count from a scalar SQL query."""

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    return int(row[0] if row else 0)


def content_body(connection: Any, repo_id: str, relative_path: str) -> str | None:
    """Return the current stored file body for one repo-relative path."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT content
            FROM content_files
            WHERE repo_id = %s
              AND relative_path = %s
            """,
            (repo_id, relative_path),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return str(row[0])


def seed_scope_generation(
    connection: Any,
    *,
    scope_id: str,
    generation_id: str,
    active_generation_id: str | None = None,
    generation_label: str,
    graph_record_id: str,
    freshness_hint: str,
    generation_status: str,
    include_fact_record: bool,
    include_work_item: bool = False,
    content_path: str | None = None,
    content_body_value: str | None = None,
    content_digest: str | None = None,
) -> None:
    """Insert or update one synthetic scope generation for the live compose proof."""

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
                scope_id,
                "repository",
                "git",
                "incremental-refresh-proof-scope",
                None,
                "git",
                scope_id,
                observed,
                now,
                "active",
                active_generation_id,
                json.dumps({"repo_id": graph_record_id}),
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
                scope_id,
                "snapshot",
                freshness_hint,
                observed,
                now,
                generation_status,
                observed if generation_status == "active" else None,
                json.dumps(
                    {"repo_id": graph_record_id, "generation": generation_label}
                ),
            ),
        )
        if include_fact_record:
            fact_payload: dict[str, Any] = {
                "graph_id": graph_record_id,
                "graph_kind": "repository",
                "name": "incremental-refresh-proof-repo",
            }
            if content_body_value is not None and content_path is not None:
                fact_payload["content_path"] = content_path
                fact_payload["content_body"] = content_body_value
                fact_payload["content_digest"] = content_digest or content_body_value
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
                    scope_id,
                    generation_id,
                    "repository",
                    f"repository:{graph_record_id}",
                    "git",
                    "incremental-refresh-proof-scope",
                    None,
                    None,
                    observed,
                    now,
                    False,
                    json.dumps(fact_payload),
                ),
            )
        if include_work_item:
            cursor.execute(
                """
                INSERT INTO fact_work_items (
                    work_item_id, scope_id, generation_id, stage, domain, status,
                    attempt_count, lease_owner, claim_until, visible_at,
                    last_attempt_at, next_attempt_at, failure_class, failure_message,
                    failure_details, payload, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, 'projector', 'source_local', 'pending',
                    0, NULL, NULL, %s, NULL, NULL, NULL, NULL,
                    NULL, '{}'::jsonb, %s, %s
                )
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
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    f"projector_{scope_id}_{generation_id}",
                    scope_id,
                    generation_id,
                    now,
                    now,
                    now,
                ),
            )


def wait_for_retrying_work_item(
    client: Any,
    connection: Any,
    *,
    scope_id: str,
    generation_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Wait until the projector emits a retrying work item for one generation."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_status = get_json(client, "/admin/status?format=json")
        if (
            count(
                connection,
                """
                SELECT COUNT(*)
                FROM fact_work_items
                WHERE scope_id = %s
                  AND generation_id = %s
                  AND stage = 'projector'
                  AND status = 'retrying'
                  AND attempt_count = 1
                """,
                (scope_id, generation_id),
            )
            >= 1
        ):
            return latest_status
        time.sleep(0.5)

    raise AssertionError(
        "projector did not surface a runtime-generated retrying work item before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )


def wait_for_projection_state(
    client: Any,
    connection: Any,
    *,
    scope_id: str,
    active_generation_id: str,
    repo_id: str,
    relative_path: str,
    expected_content_body: str,
    timeout_seconds: int,
    superseded_generation_id: str | None = None,
    minimum_projector_succeeded: int = 1,
) -> dict[str, Any]:
    """Wait until the compose stack converges on the expected projection state."""

    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_status = get_json(client, "/admin/status?format=json")
        if content_body(connection, repo_id, relative_path) != expected_content_body:
            time.sleep(1.0)
            continue
        if (
            count(
                connection,
                """
                SELECT COUNT(*)
                FROM scope_generations
                WHERE generation_id = %s
                  AND status = 'active'
                """,
                (active_generation_id,),
            )
            < 1
        ):
            time.sleep(1.0)
            continue
        if superseded_generation_id is not None and (
            count(
                connection,
                """
                SELECT COUNT(*)
                FROM scope_generations
                WHERE generation_id = %s
                  AND status = 'superseded'
                """,
                (superseded_generation_id,),
            )
            < 1
        ):
            time.sleep(1.0)
            continue
        if (
            count(
                connection,
                """
                SELECT COUNT(*)
                FROM fact_work_items
                WHERE scope_id = %s
                  AND generation_id = %s
                  AND stage = 'projector'
                  AND status = 'succeeded'
                """,
                (scope_id, active_generation_id),
            )
            < 1
        ):
            time.sleep(1.0)
            continue
        stage_rows = {
            str(stage.get("stage") or ""): stage
            for stage in list(latest_status.get("stages") or [])
            if isinstance(stage, dict)
        }
        if (
            int((stage_rows.get("projector") or {}).get("succeeded") or 0)
            < minimum_projector_succeeded
        ):
            time.sleep(1.0)
            continue
        if int((latest_status.get("queue") or {}).get("outstanding") or 0) != 0:
            time.sleep(1.0)
            continue
        return latest_status

    raise AssertionError(
        "incremental refresh did not converge before timeout; "
        f"last status was {json.dumps(latest_status, sort_keys=True)}"
    )
