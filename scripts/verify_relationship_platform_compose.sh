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
RELATIONSHIP_PLATFORM_FIXTURE_ROOT="$REPO_ROOT/tests/fixtures/relationship_platform"
REPOSITORIES_FILE="$TMP_DIR/repositories.json"
CONTEXT_FILE="$TMP_DIR/repository-context.json"
COVERAGE_FILE="$TMP_DIR/repository-coverage.json"
INDEX_STATUS_FILE="$TMP_DIR/index-status.json"
GRAPH_RELATIONSHIP_TYPES_FILE="$TMP_DIR/graph-relationship-types.txt"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
API_KEY=""
COMPOSE_CMD=()

build_relationship_platform_repo_rules_json() {
    local root="$1"
    local -a repo_ids=()

    for entry in "$root"/*; do
        if [[ ! -d "$entry" ]]; then
            continue
        fi
        repo_ids+=("$(basename "$entry")")
    done

    if [[ ${#repo_ids[@]} -eq 0 ]]; then
        echo "Relationship platform fixture root contains no repository directories: $root" >&2
        return 1
    fi

    jq -cn --args '{exact: $ARGS.positional}' "${repo_ids[@]}"
}
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

wait_for_index_completion() {
    local attempts="$1"
    local sleep_seconds="$2"

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if ! api_get "/index-status" "$INDEX_STATUS_FILE"; then
            sleep "$sleep_seconds"
            continue
        fi

        if jq -e '
            (.status // "") == "healthy" and
            ((.queue.outstanding // 0) == 0) and
            ((.queue.in_flight // 0) == 0) and
            ((.queue.pending // 0) == 0) and
            ((.queue.retrying // 0) == 0) and
            ((.queue.failed // 0) == 0)
        ' "$INDEX_STATUS_FILE" >/dev/null; then
            return 0
        fi

        sleep "$sleep_seconds"
    done

    echo "Timed out waiting for /index-status to report queue completion" >&2
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

api_post_json() {
    local path="$1"
    local payload="$2"
    local output_file="$3"
    if [[ -n "$API_KEY" ]]; then
        curl -fsS \
            -X POST \
            -H "Authorization: Bearer $API_KEY" \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "$API_BASE_URL$path" \
            >"$output_file"
    else
        curl -fsS \
            -X POST \
            -H "Content-Type: application/json" \
            -d "$payload" \
            "$API_BASE_URL$path" \
            >"$output_file"
    fi
}

repository_id_by_name() {
    local repo_name="$1"
    jq -r --arg repo_name "$repo_name" '
        def repo_rows:
            if type == "array" then
                .[]
            elif ((.repositories? // []) | length > 0) then
                .repositories[]
            elif ((.items? // []) | length > 0) then
                .items[]
            else
                empty
            end;
        first(repo_rows | select((.name // "") == $repo_name) | (.repo_id // .id // .repository_id // empty))
    ' "$REPOSITORIES_FILE"
}

verify_service_edge_api_context() {
    local repo_id
    repo_id="$(repository_id_by_name "service-edge-api")"
    if [[ -z "$repo_id" || "$repo_id" == "null" ]]; then
        echo "Could not resolve service-edge-api repository id from /repositories payload." >&2
        return 1
    fi

    api_get "/repositories/${repo_id}/context" "$CONTEXT_FILE"
    jq -e '
        (.repository.name // "") == "service-edge-api" and
        ((.relationship_overview.workflow_driven // []) | any(
            (.type // "") == "DEPLOYS_FROM" and
            (.target_name // "") == "delivery-legacy-automation" and
            (.evidence_type // "") == "github_actions_reusable_workflow_ref"
        )) and
        ((.relationship_overview.iac_driven // []) | any(
            (.type // "") == "DEPLOYS_FROM" and
            (.target_name // "") == "service-worker-jobs" and
            (
                (.evidence_type // "") == "docker_compose_image" or
                (.evidence_type // "") == "docker_compose_build_context"
            )
        )) and
        ((.relationship_overview.iac_driven // []) | any(
            (.type // "") == "DEPENDS_ON" and
            (.target_name // "") == "service-worker-jobs" and
            (.evidence_type // "") == "docker_compose_depends_on"
        )) and
        ((.infrastructure_overview.artifact_family_counts.github_actions // 0) >= 1) and
        ((.infrastructure_overview.artifact_family_counts.docker // 0) >= 1) and
        ((.deployment_artifacts.deployment_artifacts // []) | any(
            (.artifact_type // "") == "docker_compose" and
            (.relative_path // "") == "docker-compose.yaml" and
            (.service_name // "") == "edge-api"
        )) and
        ((.deployment_artifacts.deployment_artifacts // []) | any(
            (.artifact_type // "") == "docker_compose" and
            (.relative_path // "") == "docker-compose.yaml" and
            (.service_name // "") == "service-worker-jobs"
        ))
    ' "$CONTEXT_FILE" >/dev/null
}

verify_service_worker_jobs_context() {
    local repo_id
    repo_id="$(repository_id_by_name "service-worker-jobs")"
    if [[ -z "$repo_id" || "$repo_id" == "null" ]]; then
        echo "Could not resolve service-worker-jobs repository id from /repositories payload." >&2
        return 1
    fi

    api_get "/repositories/${repo_id}/context" "$CONTEXT_FILE"
    jq -e '
        (.repository.name // "") == "service-worker-jobs" and
        ((.deployment_artifacts.workflow_artifacts // []) | any(
            (.relative_path // "") == ".github/workflows/deploy-gated.yml" and
            (.workflow_name // "") == "deploy-gated" and
            (.command_count // 0) == 2 and
            ((.gating_conditions // []) | length) == 2 and
            ((.needs_dependencies // []) | length) == 1
        ))
    ' "$CONTEXT_FILE" >/dev/null
}

verify_trace_deployment_chain() {
    api_post_json "/impact/trace-deployment-chain" '{"service_name":"service-edge-api"}' "$CONTEXT_FILE"
    jq -e '
        (.service_name // "") == "service-edge-api" and
        ((.story // "") | length) > 0 and
        ((.deployment_overview.platform_count // 0) >= 1) and
        ((.deployment_sources // []) | any((.repo_name // "") == "deployment-kustomize")) and
        ((.deployment_sources // []) | any((.repo_name // "") == "deployment-helm")) and
        ((.k8s_resources // []) | any((.relative_path // "") == "k8s/deployment.yaml")) and
        ((.controller_overview.controller_count // 0) >= 1) and
        ((.delivery_paths // []) | any((.type // "") == "deployment_source" and (.target // "") == "deployment-kustomize")) and
        ((.delivery_paths // []) | any((.type // "") == "deployment_source" and (.target // "") == "deployment-helm"))
    ' "$CONTEXT_FILE" >/dev/null
}

verify_api_surface() {
    local repo_id
    local relationship_repo_id

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

    relationship_repo_id="$(
        jq -r '
            def repo_ids:
                if type == "array" then
                    .[]
                elif ((.repositories? // []) | length > 0) then
                    .repositories[]
                elif ((.items? // []) | length > 0) then
                    .items[]
                else
                    empty
                end;
            [repo_ids | (.repo_id // .id // .repository_id // empty)] | .[]
        ' "$REPOSITORIES_FILE" | while read -r candidate_repo_id; do
            if [[ -z "$candidate_repo_id" ]]; then
                continue
            fi
            api_get "/repositories/${candidate_repo_id}/context" "$CONTEXT_FILE"
            if jq -e '
                (.relationship_overview.relationship_count // 0) > 0 and
                (
                    ((.relationship_overview.controller_driven // []) | length) > 0 or
                    ((.relationship_overview.workflow_driven // []) | length) > 0 or
                    ((.relationship_overview.iac_driven // []) | length) > 0
                )
            ' "$CONTEXT_FILE" >/dev/null; then
                printf "%s" "$candidate_repo_id"
                break
            fi
        done
    )"
    if [[ -z "$relationship_repo_id" ]]; then
        echo "Could not find a repository context with compose-backed typed relationship evidence." >&2
        return 1
    fi

    api_get "/repositories/${relationship_repo_id}/context" "$CONTEXT_FILE"
    jq -e '
        (.relationship_overview.relationship_count // 0) > 0 and
        ((.relationship_overview.story // "") | length) > 0 and
        (
            ((.relationship_overview.controller_driven // []) | length) > 0 or
            ((.relationship_overview.workflow_driven // []) | length) > 0 or
            ((.relationship_overview.iac_driven // []) | length) > 0
        )
    ' "$CONTEXT_FILE" >/dev/null

    verify_service_edge_api_context
    verify_service_worker_jobs_context
    verify_trace_deployment_chain
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

    "${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell \
        -u neo4j \
        -p "${PCG_NEO4J_PASSWORD:-change-me}" \
        --format plain \
        "MATCH ()-[rel:DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|RUNS_ON]->() RETURN DISTINCT type(rel) ORDER BY type(rel)" \
        >"$GRAPH_RELATIONSHIP_TYPES_FILE"
    if ! rg -q 'DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|RUNS_ON' "$GRAPH_RELATIONSHIP_TYPES_FILE"; then
        echo "Expected at least one typed relationship family in Neo4j, got:" >&2
        cat "$GRAPH_RELATIONSHIP_TYPES_FILE" >&2
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

if [[ -z "${PCG_FILESYSTEM_HOST_ROOT:-}" ]]; then
    export PCG_FILESYSTEM_HOST_ROOT="$RELATIONSHIP_PLATFORM_FIXTURE_ROOT"
fi
if [[ -z "${PCG_REPOSITORY_RULES_JSON:-}" ]]; then
    PCG_REPOSITORY_RULES_JSON="$(build_relationship_platform_repo_rules_json "$PCG_FILESYSTEM_HOST_ROOT")"
    export PCG_REPOSITORY_RULES_JSON
fi

"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
compose_started=false
for attempt in 1 2; do
    configure_ports
    echo "Starting local compose stack..."
    echo "Using host ports: api=$PCG_HTTP_PORT postgres=$PCG_POSTGRES_PORT neo4j_bolt=$NEO4J_BOLT_PORT jaeger=$JAEGER_UI_PORT"
    echo "Using fixture root: $PCG_FILESYSTEM_HOST_ROOT"
    echo "Using repository rules: $PCG_REPOSITORY_RULES_JSON"
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

echo "Waiting for /index-status queue completion..."
wait_for_index_completion 180 5

echo "Verifying relationship platform API and graph state..."
verify_api_surface
verify_graph_state

echo
echo "Relationship-platform compose verification passed."
echo "API: $API_BASE_URL"
echo "Jaeger UI: $JAEGER_URL"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
