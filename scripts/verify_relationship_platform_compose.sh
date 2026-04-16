#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_PORT="${PCG_HTTP_PORT:-8080}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"
JAEGER_PORT="${JAEGER_UI_PORT:-16686}"
API_BASE_URL="http://localhost:${API_PORT}/api/v0"
JAEGER_URL="http://localhost:${JAEGER_PORT}"
TMP_DIR="$(mktemp -d)"
REPOSITORIES_FILE="$TMP_DIR/repositories.json"
CONTEXT_FILE="$TMP_DIR/repository-context.json"
COVERAGE_FILE="$TMP_DIR/repository-coverage.json"
INDEX_STATUS_FILE="$TMP_DIR/index-status.json"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
API_KEY=""
COMPOSE_CMD=()
COMPOSE_DISPLAY=""

cleanup() {
    local exit_code=$?
    if [[ "$exit_code" -ne 0 ]]; then
        echo
        echo "Relationship-platform compose verification failed."
        echo "Useful logs:"
        echo "  $COMPOSE_DISPLAY logs --tail=200 platform-context-graph"
        echo "  $COMPOSE_DISPLAY logs --tail=200 bootstrap-index"
        echo "  $COMPOSE_DISPLAY logs --tail=200 neo4j"
        if [[ -f "$INDEX_STATUS_FILE" ]]; then
            echo "Last index-status payload:"
            cat "$INDEX_STATUS_FILE"
        fi
        echo "Jaeger UI: $JAEGER_URL"
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

    for ((attempt = 1; attempt <= attempts; attempt++)); do
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
        state="$(docker inspect --format='{{.State.Status}}' "$container_id" 2>/dev/null || true)"
        if [[ -z "$state" ]]; then
            sleep 2
            continue
        fi
        if [[ "$state" == "exited" ]]; then
            local exit_code
            exit_code="$(docker inspect --format='{{.State.ExitCode}}' "$container_id" 2>/dev/null || true)"
            if [[ -z "$exit_code" ]]; then
                sleep 2
                continue
            fi
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
        'token="${PCG_API_KEY:-}";
         if [ -n "$token" ]; then
             printf %s "$token";
             exit 0;
         fi
         home="${PCG_HOME:-/data/.platform-context-graph}";
         if [ -f "$home/.env" ]; then
             sed -n "s/^PCG_API_KEY=//p" "$home/.env" | tail -n 1 | tr -d "\n";
         fi'
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
    NEO4J_BOLT_PORT="$NEO4J_BOLT_PORT"
    JAEGER_PORT="$JAEGER_UI_PORT"
    API_BASE_URL="http://localhost:${API_PORT}/api/v0"
    JAEGER_URL="http://localhost:${JAEGER_PORT}"
}

refresh_compose_ports() {
    local mapped

    mapped="$("${COMPOSE_CMD[@]}" port platform-context-graph 8080 | tail -n 1)"
    if [[ -z "$mapped" ]]; then
        echo "Could not determine the published API port from compose." >&2
        return 1
    fi
    export PCG_HTTP_PORT="${mapped##*:}"

    mapped="$("${COMPOSE_CMD[@]}" port neo4j 7687 | tail -n 1)"
    if [[ -z "$mapped" ]]; then
        echo "Could not determine the published Neo4j Bolt port from compose." >&2
        return 1
    fi
    export NEO4J_BOLT_PORT="${mapped##*:}"

    mapped="$("${COMPOSE_CMD[@]}" port jaeger 16686 | tail -n 1)"
    if [[ -z "$mapped" ]]; then
        echo "Could not determine the published Jaeger port from compose." >&2
        return 1
    fi
    export JAEGER_PORT="${mapped##*:}"

    API_PORT="$PCG_HTTP_PORT"
    API_BASE_URL="http://localhost:${API_PORT}/api/v0"
    JAEGER_URL="http://localhost:${JAEGER_PORT}"
}

api_get() {
    local path="$1"
    local output_file="$2"
    if [[ -n "$API_KEY" ]]; then
        curl -fsS \
            -H "Authorization: Bearer $API_KEY" \
            "$API_BASE_URL$path" \
            >"$output_file"
    else
        curl -fsS \
            "$API_BASE_URL$path" \
            >"$output_file"
    fi
}

verify_api_surface() {
    local repo_id

    api_get "/repositories" "$REPOSITORIES_FILE"
    jq -e '
        (type == "array" and length > 0) or
        (
            type == "object" and
            (
                ((.repositories? // []) | length > 0) or
                ((.items? // []) | length > 0)
            )
        )
    ' "$REPOSITORIES_FILE" >/dev/null

    repo_id="$(jq -r '
        if type == "array" then
            (.[0].repo_id // .[0].id // .[0].repository_id // empty)
        elif ((.repositories? // []) | length > 0) then
            (.repositories[0].repo_id // .repositories[0].id // .repositories[0].repository_id // empty)
        elif ((.items? // []) | length > 0) then
            (.items[0].repo_id // .items[0].id // .items[0].repository_id // empty)
        else
            empty
        end
    ' "$REPOSITORIES_FILE")"
    if [[ -z "$repo_id" ]]; then
        echo "Could not determine repository id from /repositories payload" >&2
        return 1
    fi

    api_get "/repositories/${repo_id}/context" "$CONTEXT_FILE"
    api_get "/repositories/${repo_id}/coverage" "$COVERAGE_FILE"
    api_get "/index-status" "$INDEX_STATUS_FILE"

    jq -e 'type == "object" and length > 0' "$CONTEXT_FILE" >/dev/null
    jq -e 'type == "object" and length > 0' "$COVERAGE_FILE" >/dev/null
    jq -e 'type == "object" and length > 0' "$INDEX_STATUS_FILE" >/dev/null
}

verify_graph_state() {
    local result
    result="$("${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell \
        -u neo4j \
        -p "${PCG_NEO4J_PASSWORD:-change-me}" \
        --format plain \
        "MATCH (n:Repository) RETURN count(n) AS count")"
    result="$(printf '%s\n' "$result" | tail -n 1)"
    if ! printf '%s\n' "$result" | rg -q '^[1-9][0-9]*$'; then
        echo "Expected Repository nodes in Neo4j, got: $result" >&2
        return 1
    fi
}

require_tool curl
require_tool docker
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

"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
compose_started=false
for attempt in 1 2; do
    configure_ports
    echo "Starting local compose stack..."
    echo "Using host ports: api=$PCG_HTTP_PORT postgres=$PCG_POSTGRES_PORT neo4j_bolt=$NEO4J_BOLT_PORT jaeger=$JAEGER_UI_PORT"
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

refresh_compose_ports
echo "Waiting for bootstrap indexing to finish..."
wait_for_bootstrap_exit 600

echo "Waiting for API health..."
wait_for_http "http://localhost:${API_PORT}/health" 60 2

echo "Reading API bearer token from the running API container..."
API_KEY="$(read_api_key)"
if [[ -n "$API_KEY" ]]; then
    echo "Found PCG_API_KEY in the API container environment."
else
    echo "No PCG_API_KEY is set in the API container; using unauthenticated local API access."
fi

echo "Verifying relationship platform API and graph state..."
verify_api_surface
verify_graph_state

echo
echo "Relationship-platform compose verification passed."
echo "API: $API_BASE_URL"
echo "Jaeger UI: $JAEGER_URL"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
