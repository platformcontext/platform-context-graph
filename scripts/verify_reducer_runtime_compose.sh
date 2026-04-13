#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMEOUT_SECONDS="${PCG_E2E_TIMEOUT_SECONDS:-180}"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
TMP_DIR="$(mktemp -d)"
REDUCER_LOG="$TMP_DIR/reducer.log"
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
REDUCER_PID=""

POSTGRES_PORT_BASE="${PCG_POSTGRES_PORT:-25432}"

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
		echo "  $COMPOSE_DISPLAY logs --tail=200 postgres"
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
	POSTGRES_DSN="postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@localhost:${PCG_POSTGRES_PORT}/platform_context_graph"
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

start_reducer() {
	echo "Launching reducer runtime..."
	(
		cd "$REPO_ROOT/go"
		PCG_LISTEN_ADDR="127.0.0.1:${PCG_REDUCER_HTTP_PORT}" \
		PCG_METRICS_ADDR="127.0.0.1:${PCG_REDUCER_METRICS_PORT}" \
		PCG_POSTGRES_DSN="$POSTGRES_DSN" \
		PCG_CONTENT_STORE_DSN="$POSTGRES_DSN" \
		PCG_DEPLOYMENT_ENVIRONMENT="reducer-compose-smoke" \
		go run ./cmd/reducer >"$REDUCER_LOG" 2>&1
	) &
	REDUCER_PID="$!"
}

run_pytest() {
	echo "Running reducer runtime smoke pytest..."
	PCG_E2E_REDUCER_BASE_URL="http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}" \
	PCG_E2E_POSTGRES_DSN="$POSTGRES_DSN" \
	PCG_E2E_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
	PYTHONPATH=src \
	uv run \
		--with httpx \
		--with 'psycopg[binary]' \
		--with psycopg_pool \
		pytest tests/e2e/test_reducer_runtime_compose.py -q
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

export PCG_REDUCER_HTTP_PORT="${PCG_REDUCER_HTTP_PORT:-28081}"
export PCG_REDUCER_METRICS_PORT="${PCG_REDUCER_METRICS_PORT:-29468}"

configure_runtime_addresses
echo "Starting compose-backed postgres..."
echo "Using host ports: postgres=$PCG_POSTGRES_PORT reducer_http=$PCG_REDUCER_HTTP_PORT"
"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
if ! "${COMPOSE_CMD[@]}" up -d postgres; then
	echo "Could not start compose-backed postgres." >&2
	exit 1
fi

wait_for_postgres 60
bootstrap_data_plane_schema
start_reducer
wait_for_http "http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}/healthz" 60 1
wait_for_http "http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}/readyz" 60 1
run_pytest

echo
echo "reducer runtime compose verification passed."
echo "Reducer admin: http://127.0.0.1:${PCG_REDUCER_HTTP_PORT}"
echo "Reducer log: $REDUCER_LOG"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
