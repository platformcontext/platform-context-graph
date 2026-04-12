#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMEOUT_SECONDS="${PCG_E2E_TIMEOUT_SECONDS:-180}"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
TMP_DIR="$(mktemp -d)"
FIXTURE_ROOT="$TMP_DIR/fixtures"
PROOF_REPO_ROOT="$FIXTURE_ROOT/proof-repo"
COLLECTOR_LOG="$TMP_DIR/collector-git.log"
BRIDGE_RAW_OUTPUT="$TMP_DIR/bridge-raw.json"
PYTHON_BRIDGE_SHIM="$TMP_DIR/python-bridge.sh"
POSTGRES_PORT_BASE="${PCG_POSTGRES_PORT:-25432}"
JAEGER_UI_PORT_BASE="${JAEGER_UI_PORT:-26686}"
OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE="${OTEL_COLLECTOR_OTLP_GRPC_PORT:-24317}"
OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE="${OTEL_COLLECTOR_OTLP_HTTP_PORT:-24318}"
OTEL_COLLECTOR_PROMETHEUS_PORT_BASE="${OTEL_COLLECTOR_PROMETHEUS_PORT:-29464}"
PCG_COLLECTOR_GIT_HTTP_PORT_BASE="${PCG_COLLECTOR_GIT_HTTP_PORT:-28080}"
PCG_COLLECTOR_GIT_METRICS_PORT_BASE="${PCG_COLLECTOR_GIT_METRICS_PORT:-29467}"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
COLLECTOR_PID=""

cleanup() {
    local exit_code=$?
    if [[ -n "$COLLECTOR_PID" ]] && kill -0 "$COLLECTOR_PID" >/dev/null 2>&1; then
        kill "$COLLECTOR_PID" >/dev/null 2>&1 || true
        wait "$COLLECTOR_PID" >/dev/null 2>&1 || true
    fi

    if [[ "$exit_code" -ne 0 ]]; then
        echo
        echo "collector-git runtime compose verification failed."
        echo "Useful logs:"
        echo "  collector log: $COLLECTOR_LOG"
        if [[ -s "$COLLECTOR_LOG" ]]; then
            echo "  collector log tail:"
            tail -n 200 "$COLLECTOR_LOG" || true
        fi
        if [[ -s "$BRIDGE_RAW_OUTPUT" ]]; then
            echo "  bridge raw output tail:"
            tail -n 20 "$BRIDGE_RAW_OUTPUT" || true
        fi
        echo "  $COMPOSE_DISPLAY logs --tail=200 postgres"
        echo "  $COMPOSE_DISPLAY logs --tail=200 otel-collector"
        echo "Jaeger UI: http://localhost:${JAEGER_UI_PORT}"
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

wait_for_http() {
    local url="$1"
    local attempts="$2"
    local sleep_seconds="$3"

    for ((attempt=1; attempt<=attempts; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        if [[ -n "$COLLECTOR_PID" ]] && ! kill -0 "$COLLECTOR_PID" >/dev/null 2>&1; then
            echo "collector-git exited before $url became ready" >&2
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

configure_runtime_addresses() {
    export PCG_POSTGRES_PORT="$(pick_port "$POSTGRES_PORT_BASE")"
    export JAEGER_UI_PORT="$(pick_port "$JAEGER_UI_PORT_BASE")"
    export OTEL_COLLECTOR_OTLP_GRPC_PORT="$(pick_port "$OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE")"
    export OTEL_COLLECTOR_OTLP_HTTP_PORT="$(pick_port "$OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE")"
    export OTEL_COLLECTOR_PROMETHEUS_PORT="$(pick_port "$OTEL_COLLECTOR_PROMETHEUS_PORT_BASE")"
    export PCG_COLLECTOR_GIT_HTTP_PORT="$(pick_port "$PCG_COLLECTOR_GIT_HTTP_PORT_BASE")"
    export PCG_COLLECTOR_GIT_METRICS_PORT="$(pick_port "$PCG_COLLECTOR_GIT_METRICS_PORT_BASE")"
    POSTGRES_DSN="postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@localhost:${PCG_POSTGRES_PORT}/platform_context_graph"
}

start_compose_infra() {
    for attempt in 1 2; do
        configure_runtime_addresses
        echo "Starting compose-backed infrastructure..."
        echo "Using host ports: postgres=$PCG_POSTGRES_PORT jaeger=$JAEGER_UI_PORT collector_http=$PCG_COLLECTOR_GIT_HTTP_PORT"
        "${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
        if "${COMPOSE_CMD[@]}" up -d postgres jaeger otel-collector; then
            return 0
        fi
        if [[ "$attempt" -eq 2 ]]; then
            break
        fi
        echo "Compose startup failed; retrying with a clean stack..."
        sleep 2
    done
    echo "Could not start compose-backed infrastructure after retrying." >&2
    return 1
}

write_python_bridge_shim() {
    cat >"$PYTHON_BRIDGE_SHIM" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

exec uv run \
    --with httpx \
    --with 'psycopg[binary]' \
    --with psycopg_pool \
    python "$@"
EOF
    chmod 755 "$PYTHON_BRIDGE_SHIM"
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

prepare_fixture_root() {
    mkdir -p "$PROOF_REPO_ROOT"
    cp "$REPO_ROOT/tests/fixtures/ecosystems/code_only_python/app.py" "$PROOF_REPO_ROOT/app.py"
}

start_collector() {
    echo "Launching external collector-git runtime..."
    (
        cd "$REPO_ROOT/go"
        PCG_LISTEN_ADDR="127.0.0.1:${PCG_COLLECTOR_GIT_HTTP_PORT}" \
        PCG_METRICS_ADDR="127.0.0.1:${PCG_COLLECTOR_GIT_METRICS_PORT}" \
        PCG_POSTGRES_DSN="$POSTGRES_DSN" \
        PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
        PCG_REPO_SOURCE_MODE="filesystem" \
        PCG_FILESYSTEM_ROOT="$FIXTURE_ROOT" \
        PCG_REPOS_DIR="$TMP_DIR/repos" \
        PCG_GIT_AUTH_METHOD="none" \
        PCG_REPOSITORY_RULES_JSON="[]" \
        PCG_REPO_ROOT="$REPO_ROOT" \
        PCG_PYTHON_EXECUTABLE="$PYTHON_BRIDGE_SHIM" \
        PCG_HOME="$TMP_DIR/.platform-context-graph" \
        PCG_DEPLOYMENT_ENVIRONMENT="collector-git-compose-smoke" \
        PCG_BRIDGE_RAW_OUTPUT_PATH="$BRIDGE_RAW_OUTPUT" \
        OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:${OTEL_COLLECTOR_OTLP_GRPC_PORT}" \
        OTEL_EXPORTER_OTLP_PROTOCOL="grpc" \
        OTEL_EXPORTER_OTLP_INSECURE="true" \
        OTEL_TRACES_EXPORTER="otlp" \
        OTEL_METRICS_EXPORTER="none" \
        OTEL_LOGS_EXPORTER="none" \
        go run ./cmd/collector-git >"$COLLECTOR_LOG" 2>&1
    ) &
    COLLECTOR_PID="$!"
}

run_pytest() {
    echo "Running collector-git runtime smoke pytest..."
    PCG_E2E_COLLECTOR_BASE_URL="http://127.0.0.1:${PCG_COLLECTOR_GIT_HTTP_PORT}" \
    PCG_E2E_POSTGRES_DSN="$POSTGRES_DSN" \
    PCG_E2E_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
    PYTHONPATH=src \
    uv run \
        --with httpx \
        --with 'psycopg[binary]' \
        --with psycopg_pool \
        pytest tests/e2e/test_collector_git_runtime_compose.py -q
}

require_tool docker
require_tool curl
require_tool python3
require_tool go
require_tool uv

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

prepare_fixture_root
write_python_bridge_shim
start_compose_infra
wait_for_postgres 60
bootstrap_data_plane_schema
start_collector
wait_for_http "http://127.0.0.1:${PCG_COLLECTOR_GIT_HTTP_PORT}/healthz" 60 1
wait_for_http "http://127.0.0.1:${PCG_COLLECTOR_GIT_HTTP_PORT}/readyz" 60 1
run_pytest

echo
echo "collector-git runtime compose verification passed."
echo "Collector admin: http://127.0.0.1:${PCG_COLLECTOR_GIT_HTTP_PORT}"
echo "Collector log: $COLLECTOR_LOG"
echo "Jaeger UI: http://localhost:${JAEGER_UI_PORT}"
