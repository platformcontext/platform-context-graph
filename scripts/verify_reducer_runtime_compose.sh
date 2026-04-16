#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
TMP_DIR="$(mktemp -d)"
REDUCER_LOG="$TMP_DIR/reducer.log"
STATUS_FILE="$TMP_DIR/reducer-status.json"
METRICS_FILE="$TMP_DIR/reducer-metrics.txt"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
REDUCER_PID=""
POSTGRES_DSN=""

POSTGRES_PORT_BASE="${PCG_POSTGRES_PORT:-25432}"
PCG_REDUCER_HTTP_PORT_BASE="${PCG_REDUCER_HTTP_PORT:-28082}"
NEO4J_HTTP_PORT_BASE="${NEO4J_HTTP_PORT:-27474}"
NEO4J_BOLT_PORT_BASE="${NEO4J_BOLT_PORT:-27687}"

cleanup() {
    local exit_code=$?
    if [[ -n "$REDUCER_PID" ]] && kill -0 "$REDUCER_PID" >/dev/null 2>&1; then
        kill "$REDUCER_PID" >/dev/null 2>&1 || true
        wait "$REDUCER_PID" >/dev/null 2>&1 || true
    fi

    if [[ "$exit_code" -ne 0 ]]; then
        echo
        echo "reducer runtime compose verification failed."
        echo "Useful logs:"
        echo "  reducer log: $REDUCER_LOG"
        if [[ -s "$REDUCER_LOG" ]]; then
            echo "  reducer log tail:"
            tail -n 200 "$REDUCER_LOG" || true
        fi
        if [[ -s "$STATUS_FILE" ]]; then
            echo "  reducer status:"
            cat "$STATUS_FILE"
        fi
        if [[ -s "$METRICS_FILE" ]]; then
            echo "  reducer metrics tail:"
            tail -n 40 "$METRICS_FILE" || true
        fi
        echo "  $COMPOSE_DISPLAY logs --tail=200 postgres"
        echo "  $COMPOSE_DISPLAY logs --tail=200 neo4j"
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
    local port
    for ((port = start_port; port < start_port + 200; port++)); do
        if ! nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
            echo "$port"
            return 0
        fi
    done
    echo "no free port found near $start_port" >&2
    return 1
}

wait_for_http() {
    local url="$1"
    local attempts="$2"
    local sleep_seconds="$3"

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        if [[ -n "$REDUCER_PID" ]] && ! kill -0 "$REDUCER_PID" >/dev/null 2>&1; then
            echo "reducer exited before $url became ready" >&2
            return 1
        fi
        sleep "$sleep_seconds"
    done
    echo "Timed out waiting for $url" >&2
    return 1
}

wait_for_postgres() {
    local attempts="$1"
    for ((attempt = 1; attempt <= attempts; attempt++)); do
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
    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if "${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell -u neo4j -p "${PCG_NEO4J_PASSWORD:-change-me}" "RETURN 1" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "Timed out waiting for neo4j readiness" >&2
    return 1
}

configure_runtime_addresses() {
    export PCG_POSTGRES_PORT="$(pick_port "$POSTGRES_PORT_BASE")"
    export PCG_REDUCER_HTTP_PORT="$(pick_port "$PCG_REDUCER_HTTP_PORT_BASE")"
    export NEO4J_HTTP_PORT="$(pick_port "$NEO4J_HTTP_PORT_BASE")"
    export NEO4J_BOLT_PORT="$(pick_port "$NEO4J_BOLT_PORT_BASE")"
    POSTGRES_DSN="postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@localhost:${PCG_POSTGRES_PORT}/platform_context_graph"
}

bootstrap_data_plane_schema() {
    echo "Applying Go data-plane schema bootstrap..."
    (
        cd "$REPO_ROOT/go"
        PCG_POSTGRES_DSN="$POSTGRES_DSN" \
        PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
        PCG_NEO4J_URI="bolt://localhost:${NEO4J_BOLT_PORT}" \
        PCG_NEO4J_USERNAME="neo4j" \
        PCG_NEO4J_PASSWORD="${PCG_NEO4J_PASSWORD:-change-me}" \
        NEO4J_URI="bolt://localhost:${NEO4J_BOLT_PORT}" \
        NEO4J_USERNAME="neo4j" \
        NEO4J_PASSWORD="${PCG_NEO4J_PASSWORD:-change-me}" \
        go run ./cmd/bootstrap-data-plane
    )
}

start_reducer() {
    echo "Launching reducer runtime..."
    (
        cd "$REPO_ROOT/go"
        PCG_LISTEN_ADDR="127.0.0.1:${PCG_REDUCER_HTTP_PORT}" \
        PCG_POSTGRES_DSN="$POSTGRES_DSN" \
        PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
        DEFAULT_DATABASE="neo4j" \
        NEO4J_URI="bolt://localhost:${NEO4J_BOLT_PORT}" \
        NEO4J_USERNAME="neo4j" \
        NEO4J_PASSWORD="${PCG_NEO4J_PASSWORD:-change-me}" \
        PCG_DEPLOYMENT_ENVIRONMENT="reducer-compose-smoke" \
        go run ./cmd/reducer >"$REDUCER_LOG" 2>&1
    ) &
    REDUCER_PID="$!"
}

verify_reducer_surfaces() {
    echo "Capturing reducer admin status and metrics..."
    curl -fsS "http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}/admin/status?format=json" >"$STATUS_FILE"
    curl -fsS "http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}/metrics" >"$METRICS_FILE"

    jq -e '
        (.health.state | type) == "string" and
        ((.flow // []) | map(select(.lane == "reducer")) | length) == 1
    ' "$STATUS_FILE" >/dev/null
    rg -q 'pcg_runtime_info\{service_name="reducer"' "$METRICS_FILE"
    rg -q 'pcg_runtime_health_state\{service_name="reducer"' "$METRICS_FILE"
}

require_tool curl
require_tool docker
require_tool go
require_tool jq
require_tool nc
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

configure_runtime_addresses
echo "Starting compose-backed reducer infrastructure..."
echo "Using host ports: postgres=$PCG_POSTGRES_PORT neo4j_http=$NEO4J_HTTP_PORT neo4j_bolt=$NEO4J_BOLT_PORT reducer_http=$PCG_REDUCER_HTTP_PORT"
"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
if ! "${COMPOSE_CMD[@]}" up -d postgres neo4j; then
    echo "Could not start compose-backed reducer infrastructure." >&2
    exit 1
fi

wait_for_postgres 60
wait_for_neo4j 60
bootstrap_data_plane_schema
start_reducer
wait_for_http "http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}/healthz" 60 1
wait_for_http "http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}/readyz" 60 1
verify_reducer_surfaces

echo
echo "reducer runtime compose verification passed."
echo "Reducer admin: http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}"
echo "Reducer log: $REDUCER_LOG"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
