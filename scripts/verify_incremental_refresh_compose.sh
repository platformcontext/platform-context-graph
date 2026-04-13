#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMEOUT_SECONDS="${PCG_E2E_TIMEOUT_SECONDS:-180}"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
TMP_DIR="$(mktemp -d)"
PROOF_LOG="$TMP_DIR/incremental-refresh.log"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
POSTGRES_DSN=""
PROJECTOR_PID=""

PROJECTOR_HTTP_PORT_BASE="${PCG_PROJECTOR_HTTP_PORT:-28081}"
PROJECTOR_METRICS_PORT_BASE="${PCG_PROJECTOR_METRICS_PORT:-29468}"
POSTGRES_PORT_BASE="${PCG_POSTGRES_PORT:-25432}"
NEO4J_HTTP_PORT_BASE="${NEO4J_HTTP_PORT:-27474}"
NEO4J_BOLT_PORT_BASE="${NEO4J_BOLT_PORT:-27687}"
JAEGER_UI_PORT_BASE="${JAEGER_UI_PORT:-26686}"
OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE="${OTEL_COLLECTOR_OTLP_GRPC_PORT:-24317}"
OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE="${OTEL_COLLECTOR_OTLP_HTTP_PORT:-24318}"
OTEL_COLLECTOR_PROMETHEUS_PORT_BASE="${OTEL_COLLECTOR_PROMETHEUS_PORT:-29464}"
PROJECTOR_RETRY_ONCE_SCOPE_GENERATION="${PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION:-scope-incremental-refresh:generation-incremental-refresh-b}"

cleanup() {
    local exit_code=$?
    if [[ -n "$PROJECTOR_PID" ]] && kill -0 "$PROJECTOR_PID" >/dev/null 2>&1; then
        kill "$PROJECTOR_PID" >/dev/null 2>&1 || true
        wait "$PROJECTOR_PID" >/dev/null 2>&1 || true
    fi

    if [[ "$exit_code" -ne 0 ]]; then
        echo
        echo "incremental refresh compose verification failed."
        echo "Useful logs:"
        echo "  proof log: $PROOF_LOG"
        if [[ -s "$PROOF_LOG" ]]; then
            echo "  proof log tail:"
            tail -n 200 "$PROOF_LOG" || true
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

start_projector() {
    echo "Launching projector runtime..."
    (
        cd "$REPO_ROOT/go"
        PCG_LISTEN_ADDR="127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}" \
        PCG_METRICS_ADDR="127.0.0.1:${PCG_PROJECTOR_METRICS_PORT}" \
        PCG_POSTGRES_DSN="$POSTGRES_DSN" \
        PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
        PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION="$PROJECTOR_RETRY_ONCE_SCOPE_GENERATION" \
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
        go run ./cmd/projector >"$PROOF_LOG" 2>&1
    ) &
    PROJECTOR_PID="$!"
}

run_pytest() {
    echo "Running incremental refresh compose pytest (unchanged + live retry-once changed-generation proof)..."
    PCG_E2E_INCREMENTAL_REFRESH_BASE_URL="http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}" \
    PCG_E2E_POSTGRES_DSN="$POSTGRES_DSN" \
    PCG_E2E_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
    PYTHONPATH=src \
    uv run \
        --with httpx \
        --with 'psycopg[binary]' \
        pytest tests/e2e/test_incremental_refresh_compose.py -q
}

verify_neo4j_projection() {
    echo "Verifying Neo4j projection state..."
    local result
    result="$("${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell \
        -u neo4j \
        -p "${PCG_NEO4J_PASSWORD:-change-me}" \
        --format plain \
        "MATCH (n:SourceLocalRecord {record_id: 'incremental-refresh-proof-repo'}) RETURN count(n) AS count")"
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
start_projector
wait_for_http "http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}/healthz" 60 1
wait_for_http "http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}/readyz" 60 1
run_pytest
verify_neo4j_projection

echo
echo "incremental refresh compose verification passed."
echo "Projector: http://127.0.0.1:${PCG_PROJECTOR_HTTP_PORT}"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
