#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMEOUT_SECONDS="${PCG_E2E_TIMEOUT_SECONDS:-180}"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
TMP_DIR="$(mktemp -d)"
PROJECTOR_LOG="$TMP_DIR/projector.log"
PROJECTOR_HTTP_PORT_BASE="${PCG_PROJECTOR_HTTP_PORT:-28081}"
PROJECTOR_METRICS_PORT_BASE="${PCG_PROJECTOR_METRICS_PORT:-29468}"
POSTGRES_PORT_BASE="${PCG_POSTGRES_PORT:-25432}"
NEO4J_HTTP_PORT_BASE="${NEO4J_HTTP_PORT:-27474}"
NEO4J_BOLT_PORT_BASE="${NEO4J_BOLT_PORT:-27687}"
JAEGER_UI_PORT_BASE="${JAEGER_UI_PORT:-26686}"
OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE="${OTEL_COLLECTOR_OTLP_GRPC_PORT:-24317}"
OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE="${OTEL_COLLECTOR_OTLP_HTTP_PORT:-24318}"
OTEL_COLLECTOR_PROMETHEUS_PORT_BASE="${OTEL_COLLECTOR_PROMETHEUS_PORT:-29464}"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
POSTGRES_DSN=""
PROJECTOR_PID=""

cleanup() {
    local exit_code=$?
    if [[ -n "$PROJECTOR_PID" ]] && kill -0 "$PROJECTOR_PID" >/dev/null 2>&1; then
        kill "$PROJECTOR_PID" >/dev/null 2>&1 || true
        wait "$PROJECTOR_PID" >/dev/null 2>&1 || true
    fi

    if [[ "$exit_code" -ne 0 ]]; then
        echo
        echo "projector runtime compose verification failed."
        echo "Useful logs:"
        echo "  projector log: $PROJECTOR_LOG"
        if [[ -s "$PROJECTOR_LOG" ]]; then
            echo "  projector log tail:"
            tail -n 200 "$PROJECTOR_LOG" || true
        fi
        echo "  $COMPOSE_DISPLAY logs --tail=200 postgres"
        echo "  $COMPOSE_DISPLAY logs --tail=200 neo4j"
        echo "  $COMPOSE_DISPLAY logs --tail=200 otel-collector"
        echo "  $COMPOSE_DISPLAY logs --tail=200 jaeger"
    fi

    if [[ "$KEEP_STACK" != "true" ]]; then
        "${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
    fi
    rm -rf "$TMP_DIR"
    exit "$exit_code"
}
trap cleanup EXIT

require_tool() {
    local tool_name="$1"
    if ! command -v "$tool_name" >/dev/null 2>&1; then
        echo "Missing required tool: $tool_name" >&2
        exit 1
    fi
}

pick_port() {
    local start_port="$1"
    python3 - "$start_port" <<'PY'
import socket
import sys

start = int(sys.argv[1])
for port in range(start, start + 200):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        continue
    sock.close()
    print(port)
    break
else:
    raise SystemExit(f"no free port found near {start}")
PY
}

configure_ports() {
    export PCG_POSTGRES_PORT="$(pick_port "$POSTGRES_PORT_BASE")"
    export NEO4J_HTTP_PORT="$(pick_port "$NEO4J_HTTP_PORT_BASE")"
    export NEO4J_BOLT_PORT="$(pick_port "$NEO4J_BOLT_PORT_BASE")"
    export JAEGER_UI_PORT="$(pick_port "$JAEGER_UI_PORT_BASE")"
    export OTEL_COLLECTOR_OTLP_GRPC_PORT="$(pick_port "$OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE")"
    export OTEL_COLLECTOR_OTLP_HTTP_PORT="$(pick_port "$OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE")"
    export OTEL_COLLECTOR_PROMETHEUS_PORT="$(pick_port "$OTEL_COLLECTOR_PROMETHEUS_PORT_BASE")"
    export PCG_PROJECTOR_HTTP_PORT="$(pick_port "$PROJECTOR_HTTP_PORT_BASE")"
    export PCG_PROJECTOR_METRICS_PORT="$(pick_port "$PROJECTOR_METRICS_PORT_BASE")"

    POSTGRES_DSN="postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@localhost:${PCG_POSTGRES_PORT}/platform_context_graph"
}

wait_for_http() {
    local url="$1"
    local attempts="$2"
    local sleep_seconds="$3"

    for ((attempt=1; attempt<=attempts; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        if [[ -n "$PROJECTOR_PID" ]] && ! kill -0 "$PROJECTOR_PID" >/dev/null 2>&1; then
            echo "projector exited before $url became ready" >&2
            return 1
        fi
        sleep "$sleep_seconds"
    done
    echo "Timed out waiting for $url" >&2
    return 1
}

wait_for_postgres() {
    local attempts="$1"
    for ((attempt=1; attempt<=attempts; attempt++)); do
        if "${COMPOSE_CMD[@]}" exec -T postgres pg_isready -U pcg -d platform_context_graph >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "Timed out waiting for postgres readiness" >&2
    return 1
}

wait_for_neo4j() {
    local attempts="$1"
    for ((attempt=1; attempt<=attempts; attempt++)); do
        if "${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell -u neo4j -p "${PCG_NEO4J_PASSWORD:-change-me}" "RETURN 1" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "Timed out waiting for neo4j readiness" >&2
    return 1
}

bootstrap_data_plane_schema() {
    echo "Applying Go data-plane Postgres schema bootstrap..."
    (
        cd "$REPO_ROOT/go"
        PCG_POSTGRES_DSN="$POSTGRES_DSN" \
        PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
        go run ./cmd/bootstrap-data-plane
    )
}

seed_projector_state() {
    echo "Seeding projector proof state..."
    uv run --with 'psycopg[binary]' python - "$POSTGRES_DSN" <<'PY'
import datetime as dt
import json
import sys

import psycopg

dsn = sys.argv[1]
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
observed_at = now - dt.timedelta(minutes=5)
repo_id = "repository:r_projector_proof"
scope_id = "scope-projector-proof"
generation_id = "generation-projector-proof"

scope_payload = {
    "repo_id": repo_id,
    "source_key": "repo-projector-proof",
}
graph_fact_payload = {
    "graph_id": "repo-projector-proof",
    "graph_kind": "repository",
    "name": "projector-proof-repo",
}
content_fact_payload = {
    "content_path": "README.md",
    "content_body": "# Projector proof\n",
    "content_digest": "digest-projector-proof",
    "entity_type": "SqlTable",
    "entity_name": "public.projector_proof",
    "start_line": 1,
    "end_line": 3,
    "language": "sql",
    "source_cache": "create table public.projector_proof (id bigint);",
    "reducer_domain": "shared_identity",
    "entity_key": "repository:r_projector_proof",
    "reason": "projector live proof follow-up",
}

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cursor:
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
                "repo-projector-proof",
                None,
                "git",
                "repo-projector-proof",
                observed_at,
                now,
                "pending",
                None,
                json.dumps(scope_payload),
            ),
        )
        cursor.execute(
            """
            INSERT INTO scope_generations (
                generation_id, scope_id, trigger_kind, freshness_hint,
                observed_at, ingested_at, status, activated_at, superseded_at,
                payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb
            )
            ON CONFLICT (generation_id) DO UPDATE SET
                scope_id = EXCLUDED.scope_id,
                trigger_kind = EXCLUDED.trigger_kind,
                freshness_hint = EXCLUDED.freshness_hint,
                observed_at = EXCLUDED.observed_at,
                ingested_at = EXCLUDED.ingested_at,
                status = EXCLUDED.status,
                activated_at = EXCLUDED.activated_at,
                superseded_at = EXCLUDED.superseded_at
            """,
            (
                generation_id,
                scope_id,
                "snapshot",
                "",
                observed_at,
                now,
                "pending",
                None,
                None,
            ),
        )
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
                "fact-projector-graph",
                scope_id,
                generation_id,
                "repository",
                "repository:repo-projector-proof",
                "git",
                "repo-projector-proof",
                None,
                None,
                observed_at,
                now,
                False,
                json.dumps(graph_fact_payload),
            ),
        )
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
                "fact-projector-content",
                scope_id,
                generation_id,
                "content_entity",
                "content-entity:projector-proof",
                "git",
                "repo-projector-proof-content",
                None,
                None,
                observed_at,
                now,
                False,
                json.dumps(content_fact_payload),
            ),
        )
        cursor.execute(
            """
            INSERT INTO fact_work_items (
                work_item_id, scope_id, generation_id, stage, domain, status,
                attempt_count, lease_owner, claim_until, visible_at,
                last_attempt_at, next_attempt_at, failure_class, failure_message,
                failure_details, payload, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                NULL, '{}'::jsonb, %s, %s
            )
            ON CONFLICT (work_item_id) DO NOTHING
            """,
            (
                f"projector_{scope_id}_{generation_id}",
                scope_id,
                generation_id,
                "projector",
                "source_local",
                "pending",
                now,
                now,
            ),
        )
    conn.commit()
PY
}

start_projector() {
    echo "Launching projector runtime..."
    (
        cd "$REPO_ROOT/go"
        PCG_LISTEN_ADDR="127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}" \
        PCG_METRICS_ADDR="127.0.0.1:${PCG_PROJECTOR_METRICS_PORT}" \
        PCG_POSTGRES_DSN="$POSTGRES_DSN" \
        PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
        DEFAULT_DATABASE="neo4j" \
        NEO4J_URI="bolt://localhost:${NEO4J_BOLT_PORT}" \
        NEO4J_USERNAME="neo4j" \
        NEO4J_PASSWORD="${PCG_NEO4J_PASSWORD:-change-me}" \
        OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:${OTEL_COLLECTOR_OTLP_GRPC_PORT}" \
        OTEL_EXPORTER_OTLP_PROTOCOL="grpc" \
        OTEL_EXPORTER_OTLP_INSECURE="true" \
        OTEL_TRACES_EXPORTER="otlp" \
        OTEL_METRICS_EXPORTER="none" \
        OTEL_LOGS_EXPORTER="none" \
        go run ./cmd/projector >"$PROJECTOR_LOG" 2>&1
    ) &
    PROJECTOR_PID="$!"
}

run_pytest() {
    echo "Running projector runtime smoke pytest..."
    PCG_E2E_PROJECTOR_BASE_URL="http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}" \
    PCG_E2E_POSTGRES_DSN="$POSTGRES_DSN" \
    PCG_E2E_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
    PYTHONPATH=src \
    uv run \
        --with httpx \
        --with 'psycopg[binary]' \
        pytest tests/e2e/test_projector_runtime_compose.py -q
}

verify_neo4j_projection() {
    echo "Verifying Neo4j projection state..."
    local result
    result="$("${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell \
        -u neo4j \
        -p "${PCG_NEO4J_PASSWORD:-change-me}" \
        --format plain \
        "MATCH (n:SourceLocalRecord {record_id: 'repo-projector-proof'}) RETURN count(n) AS count")"
    if ! printf '%s\n' "$result" | rg -q '^[1-9][0-9]*$'; then
        echo "Expected at least one SourceLocalRecord in Neo4j, got: $result" >&2
        return 1
    fi
}

require_tool docker
require_tool curl
require_tool python3
require_tool go
require_tool uv
require_tool rg

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    COMPOSE_DISPLAY="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    COMPOSE_DISPLAY="docker-compose"
else
    echo "Missing required compose command: docker compose or docker-compose" >&2
    exit 1
fi

cd "$REPO_ROOT"

configure_ports

echo "Starting compose-backed infrastructure..."
echo "Using host ports: postgres=$PCG_POSTGRES_PORT neo4j_http=$NEO4J_HTTP_PORT neo4j_bolt=$NEO4J_BOLT_PORT jaeger=$JAEGER_UI_PORT projector_http=$PCG_PROJECTOR_HTTP_PORT"
for attempt in 1 2; do
    "${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
    if "${COMPOSE_CMD[@]}" up -d postgres neo4j jaeger otel-collector; then
        break
    fi
    if [[ "$attempt" -eq 2 ]]; then
        echo "Could not start compose-backed infrastructure after retrying." >&2
        exit 1
    fi
    echo "Compose startup failed; retrying with a clean stack..."
    configure_ports
    sleep 2
done

wait_for_postgres 60
wait_for_neo4j 60
bootstrap_data_plane_schema
seed_projector_state
start_projector
wait_for_http "http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}/healthz" 60 1
wait_for_http "http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}/readyz" 60 1
run_pytest
verify_neo4j_projection

echo
echo "projector runtime compose verification passed."
echo "Projector: http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
