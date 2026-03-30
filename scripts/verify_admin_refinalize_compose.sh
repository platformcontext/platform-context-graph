#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_PORT="${PCG_HTTP_PORT:-8080}"
JAEGER_PORT="${JAEGER_UI_PORT:-16686}"
API_BASE_URL="http://localhost:${API_PORT}/api/v0"
JAEGER_URL="http://localhost:${JAEGER_PORT}"
TIMEOUT_SECONDS="${PCG_E2E_TIMEOUT_SECONDS:-180}"
TMP_DIR="$(mktemp -d)"
RUN_ID_FILE="$TMP_DIR/run_id.txt"
STATUS_FILE="$TMP_DIR/status.json"
API_KEY_FILE="$TMP_DIR/api_key.txt"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""

cleanup() {
    local exit_code=$?
    if [[ "$exit_code" -ne 0 ]]; then
        local run_id=""
        if [[ -f "$RUN_ID_FILE" ]]; then
            run_id="$(<"$RUN_ID_FILE")"
        fi
        echo
        echo "Admin refinalize compose verification failed."
        if [[ -n "$run_id" ]]; then
            echo "Failing run_id: $run_id"
            echo "Run-specific logs:"
            echo "  $COMPOSE_DISPLAY logs platform-context-graph | rg '$run_id'"
        fi
        echo "Useful logs:"
        echo "  $COMPOSE_DISPLAY logs --tail=200 platform-context-graph"
        echo "  $COMPOSE_DISPLAY logs --tail=200 bootstrap-index"
        echo "  $COMPOSE_DISPLAY logs --tail=200 repo-sync"
        echo "Jaeger UI: $JAEGER_URL"
        if [[ -f "$STATUS_FILE" ]]; then
            echo "Last admin status payload:"
            cat "$STATUS_FILE"
        fi
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

wait_for_http() {
    local url="$1"
    local attempts="$2"
    local sleep_seconds="$3"

    for ((attempt=1; attempt<=attempts; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$sleep_seconds"
    done
    echo "Timed out waiting for $url" >&2
    return 1
}

wait_for_bootstrap_exit() {
    local timeout_seconds="$1"
    local deadline=$((SECONDS + timeout_seconds))

    while ((SECONDS < deadline)); do
        local container_id
        container_id="$("${COMPOSE_CMD[@]}" ps -a -q bootstrap-index)"
        if [[ -z "$container_id" ]]; then
            sleep 2
            continue
        fi
        local state
        state="$(docker inspect --format='{{.State.Status}}' "$container_id")"
        if [[ "$state" == "exited" ]]; then
            local exit_code
            exit_code="$(docker inspect --format='{{.State.ExitCode}}' "$container_id")"
            if [[ "$exit_code" != "0" ]]; then
                echo "bootstrap-index exited with code $exit_code" >&2
                return 1
            fi
            return 0
        fi
        sleep 2
    done

    echo "Timed out waiting for bootstrap-index to finish" >&2
    return 1
}

read_api_key() {
    "${COMPOSE_CMD[@]}" exec -T platform-context-graph sh -lc \
        "grep '^PCG_API_KEY=' /data/.platform-context-graph/.env | cut -d= -f2-"
}

logs_contain() {
    local pattern="$1"
    local logs_output

    logs_output="$("${COMPOSE_CMD[@]}" logs platform-context-graph 2>&1 || true)"
    printf '%s\n' "$logs_output" | rg -q --fixed-strings "$pattern"
}

require_tool docker
require_tool curl
require_tool rg
require_tool uv
require_tool python3

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

pick_port() {
    local start_port="$1"
    python3 - "$start_port" <<'PY'
import socket
import sys

start = int(sys.argv[1])
for port in range(start, start + 200):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", port))
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
    export NEO4J_HTTP_PORT="$(pick_port "${NEO4J_HTTP_PORT:-17474}")"
    export NEO4J_BOLT_PORT="$(pick_port "${NEO4J_BOLT_PORT:-17687}")"
    export PCG_POSTGRES_PORT="$(pick_port "${PCG_POSTGRES_PORT:-25432}")"
    export PCG_HTTP_PORT="$(pick_port "${PCG_HTTP_PORT:-18080}")"
    export JAEGER_UI_PORT="$(pick_port "${JAEGER_UI_PORT:-26686}")"
    export OTEL_COLLECTOR_OTLP_GRPC_PORT="$(pick_port "${OTEL_COLLECTOR_OTLP_GRPC_PORT:-24317}")"
    export OTEL_COLLECTOR_OTLP_HTTP_PORT="$(pick_port "${OTEL_COLLECTOR_OTLP_HTTP_PORT:-24318}")"
    export OTEL_COLLECTOR_PROMETHEUS_PORT="$(pick_port "${OTEL_COLLECTOR_PROMETHEUS_PORT:-29464}")"

    API_PORT="$PCG_HTTP_PORT"
    JAEGER_PORT="$JAEGER_UI_PORT"
    API_BASE_URL="http://localhost:${API_PORT}/api/v0"
    JAEGER_URL="http://localhost:${JAEGER_PORT}"
}

cd "$REPO_ROOT"

"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
compose_started=false
for attempt in 1 2; do
    configure_ports
    echo "Starting local compose stack..."
    echo "Using host ports: api=$PCG_HTTP_PORT postgres=$PCG_POSTGRES_PORT neo4j_http=$NEO4J_HTTP_PORT neo4j_bolt=$NEO4J_BOLT_PORT jaeger=$JAEGER_UI_PORT"
    if "${COMPOSE_CMD[@]}" up -d --build; then
        compose_started=true
        break
    fi
    "${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
    if [[ "$attempt" -eq 2 ]]; then
        break
    fi
    echo "Compose startup failed; retrying with fresh ports..."
    sleep 2
done

if [[ "$compose_started" != "true" ]]; then
    echo "Could not start the local compose stack after retrying." >&2
    exit 1
fi

echo "Waiting for bootstrap indexing to finish..."
wait_for_bootstrap_exit 600

echo "Waiting for API health..."
wait_for_http "http://localhost:${API_PORT}/health" 60 2

echo "Reading generated API key..."
read_api_key >"$API_KEY_FILE"
if [[ ! -s "$API_KEY_FILE" ]]; then
    echo "Could not read PCG_API_KEY from the compose service" >&2
    exit 1
fi

echo "Running compose-backed admin refinalize pytest..."
PCG_E2E_API_BASE_URL="$API_BASE_URL" \
PCG_E2E_API_KEY="$(<"$API_KEY_FILE")" \
PCG_E2E_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
PCG_E2E_RUN_ID_FILE="$RUN_ID_FILE" \
PCG_E2E_STATUS_FILE="$STATUS_FILE" \
PYTHONPATH=src \
uv run pytest tests/e2e/test_admin_refinalize_compose.py -q

RUN_ID="$(<"$RUN_ID_FILE")"
if [[ -z "$RUN_ID" ]]; then
    echo "Pytest completed without writing a run_id artifact" >&2
    exit 1
fi

echo "Verifying API logs contain the run_id and workload stage progress..."
logs_contain "$RUN_ID"
logs_contain "Re-finalization stage update: workloads"
logs_contain "admin.refinalize.completed"

echo
echo "Admin refinalize compose verification passed."
echo "run_id: $RUN_ID"
echo "Jaeger UI: $JAEGER_URL"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
