#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_PATH="${PCG_LOCAL_ECOSYSTEM_MANIFEST:-}"
TIMEOUT_SECONDS="${PCG_E2E_TIMEOUT_SECONDS:-1800}"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
KEEP_SCRATCH="${PCG_KEEP_E2E_SCRATCH:-false}"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
SCRATCH_ROOT=""
WORKSPACE_INFO_PATH=""
API_KEY_FILE=""
API_BASE_URL=""
JAEGER_URL=""
API_PORT=""
NEO4J_BOLT_PORT=""
JAEGER_PORT=""

cleanup() {
    local exit_code=$?
    if [[ "$exit_code" -ne 0 ]]; then
        echo
        echo "api-node-boats compose verification failed."
        echo "Scratch root: $SCRATCH_ROOT"
        echo "Workspace artifact: $WORKSPACE_INFO_PATH"
        echo "Manifest: ${MANIFEST_PATH:-<unset>}"
        if [[ -n "$COMPOSE_DISPLAY" ]]; then
            echo "Useful logs:"
            echo "  $COMPOSE_DISPLAY logs --tail=200 platform-context-graph"
            echo "  $COMPOSE_DISPLAY logs --tail=200 platformcontextgraph"
            echo "  $COMPOSE_DISPLAY logs --tail=200 repo-sync"
            echo "  $COMPOSE_DISPLAY logs --tail=200 bootstrap-index"
            echo "  $COMPOSE_DISPLAY logs --tail=200 neo4j"
        fi
        if [[ -n "$JAEGER_URL" ]]; then
            echo "Jaeger UI: $JAEGER_URL"
        fi
    fi

    if [[ "$KEEP_STACK" != "true" && "${#COMPOSE_CMD[@]}" -gt 0 ]]; then
        "${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
    fi
    if [[ "$exit_code" -eq 0 && "$KEEP_SCRATCH" != "true" && -n "$SCRATCH_ROOT" && -d "$SCRATCH_ROOT" ]]; then
        rm -rf "$SCRATCH_ROOT"
    fi
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
    export NEO4J_HTTP_PORT="$(pick_port "${NEO4J_HTTP_PORT:-17484}")"
    export NEO4J_BOLT_PORT="$(pick_port "${NEO4J_BOLT_PORT:-17697}")"
    export PCG_POSTGRES_PORT="$(pick_port "${PCG_POSTGRES_PORT:-25442}")"
    export PCG_HTTP_PORT="$(pick_port "${PCG_HTTP_PORT:-18090}")"
    export JAEGER_UI_PORT="$(pick_port "${JAEGER_UI_PORT:-26696}")"
    export OTEL_COLLECTOR_OTLP_GRPC_PORT="$(pick_port "${OTEL_COLLECTOR_OTLP_GRPC_PORT:-24327}")"
    export OTEL_COLLECTOR_OTLP_HTTP_PORT="$(pick_port "${OTEL_COLLECTOR_OTLP_HTTP_PORT:-24328}")"
    export OTEL_COLLECTOR_PROMETHEUS_PORT="$(pick_port "${OTEL_COLLECTOR_PROMETHEUS_PORT:-29474}")"

    API_PORT="$PCG_HTTP_PORT"
    NEO4J_BOLT_PORT="$NEO4J_BOLT_PORT"
    JAEGER_PORT="$JAEGER_UI_PORT"
    API_BASE_URL="http://localhost:${API_PORT}/api/v0"
    JAEGER_URL="http://localhost:${JAEGER_PORT}"
}

configure_resource_defaults() {
    export PCG_PARSE_WORKERS="${PCG_PARSE_WORKERS:-1}"
    export PCG_INDEX_QUEUE_DEPTH="${PCG_INDEX_QUEUE_DEPTH:-1}"
    export PCG_COMMIT_WORKERS="${PCG_COMMIT_WORKERS:-1}"
    export PCG_FILE_BATCH_SIZE="${PCG_FILE_BATCH_SIZE:-10}"
    export PCG_REPO_FILE_PARSE_MULTIPROCESS="${PCG_REPO_FILE_PARSE_MULTIPROCESS:-false}"

    export NEO4J_server_memory_heap_initial__size="${NEO4J_server_memory_heap_initial__size:-512M}"
    export NEO4J_server_memory_heap_max__size="${NEO4J_server_memory_heap_max__size:-1024M}"
    export NEO4J_server_memory_pagecache_size="${NEO4J_server_memory_pagecache_size:-512M}"
}

require_tool docker
require_tool curl
require_tool python3
require_tool uv
require_tool gh

if [[ -z "$MANIFEST_PATH" ]]; then
    echo "Set PCG_LOCAL_ECOSYSTEM_MANIFEST to a local-only api-node-boats ecosystem manifest." >&2
    exit 1
fi
if [[ ! -f "$MANIFEST_PATH" ]]; then
    echo "Manifest path does not exist: $MANIFEST_PATH" >&2
    exit 1
fi

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

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-pcg-api-node-boats-e2e}"
if [[ -n "${PCG_E2E_SCRATCH_ROOT:-}" ]]; then
    SCRATCH_ROOT="$PCG_E2E_SCRATCH_ROOT"
    mkdir -p "$SCRATCH_ROOT"
else
    mkdir -p "$REPO_ROOT/.tmp"
    SCRATCH_ROOT="$(mktemp -d "$REPO_ROOT/.tmp/api-node-boats-e2e.XXXXXX")"
fi
WORKSPACE_INFO_PATH="$SCRATCH_ROOT/workspace-session.json"
API_KEY_FILE="$SCRATCH_ROOT/api_key.txt"

echo "Preparing disposable api-node-boats workspace..."
PYTHONPATH=src \
uv run python scripts/run_api_node_boats_e2e.py prepare-workspace \
    --manifest-path "$MANIFEST_PATH" \
    --scratch-root "$SCRATCH_ROOT" \
    --output-json "$WORKSPACE_INFO_PATH"

if [[ ! -s "$WORKSPACE_INFO_PATH" ]]; then
    echo "Workspace artifact was not created: $WORKSPACE_INFO_PATH" >&2
    exit 1
fi

export PCG_FILESYSTEM_HOST_ROOT
PCG_FILESYSTEM_HOST_ROOT="$(python3 - "$WORKSPACE_INFO_PATH" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["workspace_root"])
PY
)"

"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
configure_ports
configure_resource_defaults
echo "Starting local compose stack..."
echo "Using host ports: api=$PCG_HTTP_PORT postgres=$PCG_POSTGRES_PORT neo4j_bolt=$NEO4J_BOLT_PORT jaeger=$JAEGER_UI_PORT"
echo "Workspace root: $PCG_FILESYSTEM_HOST_ROOT"
echo "Scratch root: $SCRATCH_ROOT"
echo "Resource profile: parse_workers=$PCG_PARSE_WORKERS queue_depth=$PCG_INDEX_QUEUE_DEPTH commit_workers=$PCG_COMMIT_WORKERS file_batch_size=$PCG_FILE_BATCH_SIZE neo4j_heap_max=$NEO4J_server_memory_heap_max__size neo4j_pagecache=$NEO4J_server_memory_pagecache_size"
"${COMPOSE_CMD[@]}" up -d --build neo4j postgres jaeger otel-collector bootstrap-index

echo "Waiting for bootstrap indexing to finish..."
wait_for_bootstrap_exit "$TIMEOUT_SECONDS"

echo "Starting API and repo-sync after successful bootstrap..."
"${COMPOSE_CMD[@]}" up -d --build platform-context-graph repo-sync

echo "Waiting for API health..."
wait_for_http "http://localhost:${API_PORT}/health" 120 2

echo "Reading generated API key..."
read_api_key >"$API_KEY_FILE"
if [[ ! -s "$API_KEY_FILE" ]]; then
    echo "Could not read PCG_API_KEY from the compose service" >&2
    exit 1
fi

echo "Running compose-backed api-node-boats bootstrap + scan pytest..."
PCG_E2E_API_BASE_URL="$API_BASE_URL" \
PCG_E2E_API_KEY="$(<"$API_KEY_FILE")" \
PCG_LOCAL_ECOSYSTEM_MANIFEST="$MANIFEST_PATH" \
PCG_E2E_WORKSPACE_INFO="$WORKSPACE_INFO_PATH" \
PCG_E2E_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
PYTHONPATH=src \
uv run pytest tests/e2e/test_api_node_boats_reindex_compose.py -q

echo
echo "api-node-boats compose verification passed."
echo "API: $API_BASE_URL"
echo "Jaeger UI: $JAEGER_URL"
echo "Workspace root: $PCG_FILESYSTEM_HOST_ROOT"
echo "Scratch root: $SCRATCH_ROOT"
if [[ "$KEEP_STACK" != "true" ]]; then
    echo "Stack teardown: $COMPOSE_DISPLAY down -v"
fi
