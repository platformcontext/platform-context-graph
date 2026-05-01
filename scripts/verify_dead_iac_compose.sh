#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_LIB="$REPO_ROOT/scripts/lib/compose_verification_runtime_common.sh"
ASSERT_LIB="$REPO_ROOT/scripts/lib/compose_verification_assertions.sh"
SOURCE_FIXTURE_ROOT="$REPO_ROOT/tests/fixtures/product_truth/dead_iac"
RUN_ROOT_BASE="${PCG_DEAD_IAC_RUN_ROOT:-$REPO_ROOT/.pcg-compose-runs}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-pcg-dead-iac-$$}"
RUN_ROOT="$RUN_ROOT_BASE/$COMPOSE_PROJECT_NAME"
FIXTURE_ROOT="$RUN_ROOT/repos"
TMP_DIR="$RUN_ROOT/tmp"
INDEX_STATUS_FILE="$TMP_DIR/index-status.json"
API_RESPONSE_FILE="$TMP_DIR/dead-iac-api.json"
MCP_RESPONSE_FILE="$TMP_DIR/dead-iac-mcp.json"
ROW_COUNTS_FILE="$TMP_DIR/iac-row-counts.json"
BOOTSTRAP_LOG_FILE="$TMP_DIR/bootstrap.log"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
GRAPH_BACKEND="${PCG_DEAD_IAC_GRAPH_BACKEND:-nornicdb}"
API_PORT="${PCG_HTTP_PORT:-8080}"
MCP_PORT="${PCG_MCP_PORT:-8081}"
API_BASE_URL="http://localhost:${API_PORT}/api/v0"
API_KEY=""
COMPOSE_CMD=()
COMPOSE_DISPLAY=""

NEO4J_HTTP_PORT_BASE="${NEO4J_HTTP_PORT:-27474}"
NEO4J_BOLT_PORT_BASE="${NEO4J_BOLT_PORT:-27687}"
PCG_POSTGRES_PORT_BASE="${PCG_POSTGRES_PORT:-35432}"
PCG_HTTP_PORT_BASE="${PCG_HTTP_PORT:-28080}"
JAEGER_UI_PORT_BASE="${JAEGER_UI_PORT:-36686}"
OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE="${OTEL_COLLECTOR_OTLP_GRPC_PORT:-34317}"
OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE="${OTEL_COLLECTOR_OTLP_HTTP_PORT:-34318}"
OTEL_COLLECTOR_PROMETHEUS_PORT_BASE="${OTEL_COLLECTOR_PROMETHEUS_PORT:-39464}"
PCG_API_METRICS_PORT_BASE="${PCG_API_METRICS_PORT:-29464}"
PCG_BOOTSTRAP_METRICS_PORT_BASE="${PCG_BOOTSTRAP_METRICS_PORT:-29467}"
PCG_MCP_PORT_BASE="${PCG_MCP_PORT:-28081}"
PCG_MCP_METRICS_PORT_BASE="${PCG_MCP_METRICS_PORT:-29468}"
PCG_INGESTER_METRICS_PORT_BASE="${PCG_INGESTER_METRICS_PORT:-29465}"
PCG_RESOLUTION_ENGINE_METRICS_PORT_BASE="${PCG_RESOLUTION_ENGINE_METRICS_PORT:-29466}"

source "$RUNTIME_LIB"
source "$ASSERT_LIB"

cleanup() {
	local exit_code=$?
	if [[ "$exit_code" -ne 0 ]]; then
		echo
		echo "Dead-IaC compose verification failed."
		echo "Useful logs:"
		echo "  $COMPOSE_DISPLAY logs --tail=200 bootstrap-index"
		echo "  $COMPOSE_DISPLAY logs --tail=200 platform-context-graph"
		echo "  $COMPOSE_DISPLAY logs --tail=200 mcp-server"
		[[ -f "$INDEX_STATUS_FILE" ]] && { echo "Last index-status payload:"; cat "$INDEX_STATUS_FILE"; }
	fi
	if [[ "$KEEP_STACK" != "true" ]]; then
		"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
		rm -rf "$RUN_ROOT"
	fi
	exit "$exit_code"
}
trap cleanup EXIT

require_real_directory() {
	local path="$1"
	local resolved
	[[ -d "$path" ]] || {
		echo "Not a directory: $path" >&2
		return 1
	}
	resolved="$(cd "$path" && pwd -P)"
	[[ "$resolved" == "$path" ]] || {
		echo "Directory must be real, not a symlink: $path -> $resolved" >&2
		return 1
	}
}

build_fixture_repositories() {
	rm -rf "$RUN_ROOT"
	mkdir -p "$FIXTURE_ROOT" "$TMP_DIR"
	local repo
	for repo_path in "$SOURCE_FIXTURE_ROOT"/*; do
		[[ -d "$repo_path" ]] || continue
		repo="$(basename "$repo_path")"
		mkdir -p "$FIXTURE_ROOT/$repo"
		cp -R "$repo_path/." "$FIXTURE_ROOT/$repo/"
		git -C "$FIXTURE_ROOT/$repo" init -q
		git -C "$FIXTURE_ROOT/$repo" add -A
		git -C "$FIXTURE_ROOT/$repo" \
			-c user.email=pcg-fixture@example.invalid \
			-c user.name="PCG Fixture" \
			commit --allow-empty -q -m fixture
	done
	require_real_directory "$FIXTURE_ROOT"
}

build_repo_rules_json() {
	local -a repos=()
	local repo_path
	for repo_path in "$FIXTURE_ROOT"/*; do
		[[ -d "$repo_path" ]] || continue
		repos+=("$(basename "$repo_path")")
	done
	jq -cn --args '{exact: $ARGS.positional}' "${repos[@]}"
}

configure_ports() {
	local retry_offset="${1:-0}"
	pcg_reset_reserved_ports
	pcg_assign_reserved_port NEO4J_HTTP_PORT "$((NEO4J_HTTP_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port NEO4J_BOLT_PORT "$((NEO4J_BOLT_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_POSTGRES_PORT "$((PCG_POSTGRES_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_HTTP_PORT "$((PCG_HTTP_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port JAEGER_UI_PORT "$((JAEGER_UI_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port OTEL_COLLECTOR_OTLP_GRPC_PORT "$((OTEL_COLLECTOR_OTLP_GRPC_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port OTEL_COLLECTOR_OTLP_HTTP_PORT "$((OTEL_COLLECTOR_OTLP_HTTP_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port OTEL_COLLECTOR_PROMETHEUS_PORT "$((OTEL_COLLECTOR_PROMETHEUS_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_API_METRICS_PORT "$((PCG_API_METRICS_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_BOOTSTRAP_METRICS_PORT "$((PCG_BOOTSTRAP_METRICS_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_MCP_PORT "$((PCG_MCP_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_MCP_METRICS_PORT "$((PCG_MCP_METRICS_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_INGESTER_METRICS_PORT "$((PCG_INGESTER_METRICS_PORT_BASE + retry_offset))"
	pcg_assign_reserved_port PCG_RESOLUTION_ENGINE_METRICS_PORT "$((PCG_RESOLUTION_ENGINE_METRICS_PORT_BASE + retry_offset))"
	API_PORT="$PCG_HTTP_PORT"
	MCP_PORT="$PCG_MCP_PORT"
	API_BASE_URL="http://localhost:${API_PORT}/api/v0"
}

refresh_compose_ports() {
	local mapped
	mapped="$("${COMPOSE_CMD[@]}" port platform-context-graph 8080 | tail -n 1)"
	[[ -n "$mapped" ]] || { echo "Could not determine API port." >&2; return 1; }
	export PCG_HTTP_PORT="${mapped##*:}"
	mapped="$("${COMPOSE_CMD[@]}" port mcp-server 8080 | tail -n 1)"
	[[ -n "$mapped" ]] || { echo "Could not determine MCP port." >&2; return 1; }
	export PCG_MCP_PORT="${mapped##*:}"
	API_PORT="$PCG_HTTP_PORT"
	MCP_PORT="$PCG_MCP_PORT"
	API_BASE_URL="http://localhost:${API_PORT}/api/v0"
}

api_post_envelope_json() {
	local path="$1" payload="$2" output_file="$3"
	local -a curl_args=(-fsS -X POST -H "Accept: application/pcg.envelope+json" -H "Content-Type: application/json" -d "$payload")
	[[ -z "$API_KEY" ]] || curl_args+=(-H "Authorization: Bearer $API_KEY")
	curl "${curl_args[@]}" "$API_BASE_URL$path" >"$output_file"
}

verify_api() {
	local payload
	payload="$(jq -cn --args '{repo_ids: $ARGS.positional, include_ambiguous: true, limit: 100}' \
		terraform-stack terraform-modules helm-controller helm-charts ansible-controller ansible-ops kustomize-controller kustomize-config)"
	api_post_envelope_json "/iac/dead" "$payload" "$API_RESPONSE_FILE"
	pcg_assert_json_query "$API_RESPONSE_FILE" '
		.data.truth_basis == "materialized_reducer_rows" and
		.data.analysis_status == "materialized_reachability" and
		.data.findings_count == 8 and
		((.data.findings // []) | any(.repo_name == "terraform-modules" and .artifact == "modules/orphan-cache" and .reachability == "unused")) and
		((.data.findings // []) | any(.repo_name == "terraform-modules" and .artifact == "modules/dynamic-target" and .reachability == "ambiguous")) and
		((.data.findings // []) | any(.repo_name == "helm-charts" and .artifact == "charts/orphan-worker" and .reachability == "unused")) and
		((.data.findings // []) | any(.repo_name == "helm-charts" and .artifact == "charts/dynamic-target" and .reachability == "ambiguous")) and
		((.data.findings // []) | any(.repo_name == "ansible-ops" and .artifact == "roles/orphan_maintenance" and .reachability == "unused")) and
		((.data.findings // []) | any(.repo_name == "ansible-ops" and .artifact == "roles/dynamic_role" and .reachability == "ambiguous")) and
		((.data.findings // []) | any(.repo_name == "kustomize-config" and .artifact == "base/orphan-api" and .reachability == "unused")) and
		((.data.findings // []) | any(.repo_name == "kustomize-config" and .artifact == "base/dynamic-target" and .reachability == "ambiguous")) and
		((.data.findings // []) | all(.artifact != "modules/checkout-service" and .artifact != "charts/checkout-service" and .artifact != "charts/worker-service" and .artifact != "roles/checkout_deploy" and .artifact != "base/checkout-service" and .artifact != "overlays/prod"))
	' "dead-IaC API response did not match materialized product truth"
}

verify_postgres_rows() {
	"${COMPOSE_CMD[@]}" exec -T postgres psql -U pcg -d platform_context_graph -t -A -F '|' -c \
		"SELECT family, reachability, count(*) FROM iac_reachability_rows GROUP BY family, reachability ORDER BY family, reachability;" \
		| jq -R -s 'split("\n") | map(select(length > 0) | split("|")) | map({family:.[0], reachability:.[1], count:(.[2]|tonumber)})' \
		>"$ROW_COUNTS_FILE"
	pcg_assert_json_query "$ROW_COUNTS_FILE" '
		(map(select(.reachability == "used") | .count) | add) == 6 and
		(map(select(.reachability == "unused") | .count) | add) == 4 and
		(map(select(.reachability == "ambiguous") | .count) | add) == 4 and
		(any(.family == "kustomize" and .reachability == "used" and .count == 2)) and
		(any(.family == "kustomize" and .reachability == "unused" and .count == 1)) and
		(any(.family == "kustomize" and .reachability == "ambiguous" and .count == 1))
	' "materialized IaC reachability row counts did not match expected truth"
}

verify_mcp() {
	local payload
	payload="$(jq -cn --args '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"find_dead_iac","arguments":{"repo_ids": $ARGS.positional, "include_ambiguous": true, "limit": 100}}}' \
		terraform-stack terraform-modules helm-controller helm-charts ansible-controller ansible-ops kustomize-controller kustomize-config)"
	local -a curl_args=(-fsS -X POST -H "Content-Type: application/json" -d "$payload")
	[[ -z "$API_KEY" ]] || curl_args+=(-H "Authorization: Bearer $API_KEY")
	curl "${curl_args[@]}" "http://localhost:${MCP_PORT}/mcp/message" >"$MCP_RESPONSE_FILE"
	pcg_assert_json_query "$MCP_RESPONSE_FILE" '
		.result.isError != true and
		((.result.content // []) | map(select(.type == "resource" and .resource.uri == "pcg://tool-result/envelope") | .resource.text | fromjson) | first) as $env |
		$env.data.truth_basis == "materialized_reducer_rows" and
		$env.data.analysis_status == "materialized_reachability" and
		$env.data.findings_count == 8
	' "dead-IaC MCP response did not mirror the materialized API truth"
}

pcg_require_tool curl
pcg_require_tool docker
pcg_require_tool git
pcg_require_tool jq
pcg_require_tool nc
pcg_require_tool rg

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

if [[ "$GRAPH_BACKEND" == "nornicdb" ]]; then
	COMPOSE_CMD+=(-f docker-compose.yaml -f docker-compose.nornicdb.yml)
	COMPOSE_DISPLAY+=" -f docker-compose.yaml -f docker-compose.nornicdb.yml"
else
	COMPOSE_CMD+=(-f docker-compose.yaml)
	COMPOSE_DISPLAY+=" -f docker-compose.yaml"
fi

cd "$REPO_ROOT"
build_fixture_repositories
export COMPOSE_PROJECT_NAME
export PCG_FILESYSTEM_HOST_ROOT="$FIXTURE_ROOT"
export PCG_REPOSITORY_RULES_JSON
PCG_REPOSITORY_RULES_JSON="$(build_repo_rules_json)"
export PCG_QUERY_PROFILE="${PCG_QUERY_PROFILE:-local_full_stack}"
export PCG_PG_SHARED_BUFFERS="${PCG_PG_SHARED_BUFFERS:-512MB}"
export PCG_PG_EFFECTIVE_CACHE_SIZE="${PCG_PG_EFFECTIVE_CACHE_SIZE:-2GB}"
export PCG_PG_MAINTENANCE_WORK_MEM="${PCG_PG_MAINTENANCE_WORK_MEM:-128MB}"
export GOMEMLIMIT="${GOMEMLIMIT:-2GiB}"

"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
compose_started=false
for attempt in 1 2; do
	configure_ports "$(((attempt - 1) * 25))"
	echo "Starting dead-IaC compose stack..."
	echo "Using compose project: $COMPOSE_PROJECT_NAME"
	echo "Using graph backend: $GRAPH_BACKEND"
	echo "Using fixture root: $PCG_FILESYSTEM_HOST_ROOT"
	echo "Using repository rules: $PCG_REPOSITORY_RULES_JSON"
	if "${COMPOSE_CMD[@]}" up -d --build; then
		compose_started=true
		break
	fi
	"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
	sleep 2
done
[[ "$compose_started" == "true" ]] || { echo "Could not start compose stack." >&2; exit 1; }

refresh_compose_ports
echo "Waiting for bootstrap indexing to finish..."
pcg_compose_wait_for_bootstrap_exit 1800
echo "Waiting for API and MCP health..."
pcg_compose_wait_for_http "http://localhost:${API_PORT}/health" 120 2
pcg_compose_wait_for_http "http://localhost:${MCP_PORT}/healthz" 120 2
API_KEY="$(pcg_compose_read_api_key)"
echo "Waiting for queue completion..."
pcg_compose_wait_for_index_completion 240 5 "$INDEX_STATUS_FILE"

verify_postgres_rows
verify_api
verify_mcp
"${COMPOSE_CMD[@]}" logs --no-color bootstrap-index >"$BOOTSTRAP_LOG_FILE"
rg -n "iac reachability materialized|iac_reachability_materialized" "$BOOTSTRAP_LOG_FILE" >/dev/null

echo
echo "Dead-IaC compose verification passed."
echo "API: $API_BASE_URL"
echo "MCP: http://localhost:${MCP_PORT}/mcp/message"
echo "Stack teardown: COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME $COMPOSE_DISPLAY down -v"
