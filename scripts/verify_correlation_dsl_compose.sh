#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_LIB="$REPO_ROOT/scripts/lib/correlation_dsl_compose_common.sh"
TMP_DIR="$(mktemp -d)"
CORRELATION_FIXTURE_ROOT="$REPO_ROOT/tests/fixtures/correlation_dsl"
REPOSITORIES_FILE="$TMP_DIR/repositories.json"
CONTEXT_FILE="$TMP_DIR/repository-context.json"
INDEX_STATUS_FILE="$TMP_DIR/index-status.json"
RESOLUTION_METRICS_FILE="$TMP_DIR/resolution-engine-metrics.txt"
KEEP_STACK="${PCG_KEEP_COMPOSE_STACK:-false}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-pcg-correlation-dsl-$$}"
API_PORT="${PCG_HTTP_PORT:-8080}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"
JAEGER_PORT="${JAEGER_UI_PORT:-16686}"
API_BASE_URL="http://localhost:${API_PORT}/api/v0"
JAEGER_URL="http://localhost:${JAEGER_PORT}"
API_KEY=""
COMPOSE_CMD=()
COMPOSE_DISPLAY=""
LAST_VERIFICATION_STEP=""
EXPECTED_REPOSITORIES_JSON="[]"
EXPECTED_REPO_COUNT=0
FIXTURE_REPO_NAMES=()
RESERVED_HOST_PORTS=()
PICKED_PORT=""
source "$COMMON_LIB"
cleanup() {
	local exit_code=$?
	if [[ "$exit_code" -ne 0 ]]; then
		echo
		echo "Correlation DSL compose verification failed."
		[[ -n "$LAST_VERIFICATION_STEP" ]] && echo "Last verification step: $LAST_VERIFICATION_STEP"
		[[ ${#FIXTURE_REPO_NAMES[@]} -gt 0 ]] && echo "Expected repositories: ${FIXTURE_REPO_NAMES[*]}"
		echo "Compose project: $COMPOSE_PROJECT_NAME"
		echo "Useful commands:"
		echo "  $COMPOSE_DISPLAY ps"
		echo "  $COMPOSE_DISPLAY logs --tail=200 platform-context-graph"
		echo "  $COMPOSE_DISPLAY logs --tail=200 bootstrap-index"
		echo "  $COMPOSE_DISPLAY logs --tail=200 resolution-engine"
		echo "  $COMPOSE_DISPLAY logs --tail=200 neo4j"
		"${COMPOSE_CMD[@]}" ps || true
		print_file_if_exists "Last repositories payload" "$REPOSITORIES_FILE"
		print_file_if_exists "Last repository context payload" "$CONTEXT_FILE"
		print_file_if_exists "Last index-status payload" "$INDEX_STATUS_FILE"
		print_tail_if_exists "Resolution-engine metrics sample" "$RESOLUTION_METRICS_FILE" 40
		echo "Jaeger UI: $JAEGER_URL"
	fi
	[[ "$KEEP_STACK" == "true" ]] || "${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
	rm -rf "$TMP_DIR"
	exit "$exit_code"
}
trap cleanup EXIT
wait_for_http() {
	local url="$1" attempts="$2" sleep_seconds="$3"
	for ((attempt = 1; attempt <= attempts; attempt++)); do
		curl -fsS "$url" >/dev/null 2>&1 && return 0
		/bin/sleep "$sleep_seconds"
	done
	echo "Timed out waiting for $url" >&2
	return 1
}
wait_for_bootstrap_exit() {
	local deadline=$((SECONDS + $1))
	while ((SECONDS < deadline)); do
		local container_id state exit_code
		container_id="$("${COMPOSE_CMD[@]}" ps -a -q bootstrap-index)"
		[[ -n "$container_id" ]] || {
			/bin/sleep 2
			continue
		}
		state="$(docker inspect --format='{{.State.Status}}' "$container_id" 2>/dev/null || true)"
		[[ -n "$state" ]] || {
			/bin/sleep 2
			continue
		}
		if [[ "$state" == "exited" ]]; then
			exit_code="$(docker inspect --format='{{.State.ExitCode}}' "$container_id" 2>/dev/null || true)"
			[[ -n "$exit_code" ]] || {
				/bin/sleep 2
				continue
			}
			[[ "$exit_code" == "0" ]] || {
				echo "bootstrap-index exited with code $exit_code" >&2
				return 1
			}
			return 0
		fi
		/bin/sleep 2
	done
	echo "Timed out waiting for bootstrap-index to finish" >&2
	return 1
}
wait_for_index_completion() {
	local attempts="$1" sleep_seconds="$2"
	for ((attempt = 1; attempt <= attempts; attempt++)); do
		if api_get "/index-status" "$INDEX_STATUS_FILE" &&
			jq -e '
				(.status // "") == "healthy" and
				((.queue.outstanding // 0) == 0) and
				((.queue.in_flight // 0) == 0) and
				((.queue.pending // 0) == 0) and
				((.queue.retrying // 0) == 0) and
				((.queue.failed // 0) == 0)
			' "$INDEX_STATUS_FILE" >/dev/null; then
			return 0
		fi
		/bin/sleep "$sleep_seconds"
	done
	echo "Timed out waiting for /index-status to report queue completion" >&2
	return 1
}
read_api_key() {
	"${COMPOSE_CMD[@]}" exec -T platform-context-graph sh -lc '
		token="${PCG_API_KEY:-}"
		if [ -n "$token" ]; then
			printf %s "$token"
			exit 0
		fi
		home="${PCG_HOME:-/data/.platform-context-graph}"
		if [ -f "$home/.env" ]; then
			sed -n "s/^PCG_API_KEY=//p" "$home/.env" | tail -n 1 | tr -d "\n"
		fi
	'
}
pick_port() {
	local start_port="$1" port
	for ((port = start_port; port < start_port + 200; port++)); do
		if [[ " ${RESERVED_HOST_PORTS[*]} " == *" $port "* ]]; then
			continue
		fi
		nc -z 127.0.0.1 "$port" >/dev/null 2>&1 || {
			RESERVED_HOST_PORTS+=("$port")
			PICKED_PORT="$port"
			return 0
		}
	done
	echo "no free port found near $start_port" >&2
	return 1
}
assign_port() {
	local name="$1" start_port="$2"
	pick_port "$start_port"
	printf -v "$name" '%s' "$PICKED_PORT"
	export "$name"
}
configure_ports() {
	RESERVED_HOST_PORTS=()
	assign_port NEO4J_HTTP_PORT "${NEO4J_HTTP_PORT:-17474}"
	assign_port NEO4J_BOLT_PORT "${NEO4J_BOLT_PORT:-17687}"
	assign_port PCG_POSTGRES_PORT "${PCG_POSTGRES_PORT:-25432}"
	assign_port PCG_HTTP_PORT "${PCG_HTTP_PORT:-18080}"
	assign_port PCG_MCP_PORT "${PCG_MCP_PORT:-18081}"
	assign_port JAEGER_UI_PORT "${JAEGER_UI_PORT:-26686}"
	assign_port OTEL_COLLECTOR_OTLP_GRPC_PORT "${OTEL_COLLECTOR_OTLP_GRPC_PORT:-24317}"
	assign_port OTEL_COLLECTOR_OTLP_HTTP_PORT "${OTEL_COLLECTOR_OTLP_HTTP_PORT:-24318}"
	assign_port OTEL_COLLECTOR_PROMETHEUS_PORT "${OTEL_COLLECTOR_PROMETHEUS_PORT:-29464}"
	assign_port PCG_API_METRICS_PORT "${PCG_API_METRICS_PORT:-21464}"
	assign_port PCG_BOOTSTRAP_METRICS_PORT "${PCG_BOOTSTRAP_METRICS_PORT:-21467}"
	assign_port PCG_MCP_METRICS_PORT "${PCG_MCP_METRICS_PORT:-21468}"
	assign_port PCG_INGESTER_METRICS_PORT "${PCG_INGESTER_METRICS_PORT:-21465}"
	assign_port PCG_RESOLUTION_ENGINE_METRICS_PORT "${PCG_RESOLUTION_ENGINE_METRICS_PORT:-21466}"
	refresh_runtime_endpoints "$PCG_HTTP_PORT" "$NEO4J_BOLT_PORT" "$JAEGER_UI_PORT"
}
refresh_runtime_endpoints() {
	API_PORT="$1"
	NEO4J_BOLT_PORT="$2"
	JAEGER_PORT="$3"
	API_BASE_URL="http://localhost:${API_PORT}/api/v0"
	JAEGER_URL="http://localhost:${JAEGER_PORT}"
}
refresh_compose_ports() {
	local api_port neo4j_port jaeger_port
	api_port="$("${COMPOSE_CMD[@]}" port platform-context-graph 8080 | tail -n 1)"
	neo4j_port="$("${COMPOSE_CMD[@]}" port neo4j 7687 | tail -n 1)"
	jaeger_port="$("${COMPOSE_CMD[@]}" port jaeger 16686 | tail -n 1)"
	[[ -n "$api_port" && -n "$neo4j_port" && -n "$jaeger_port" ]] || {
		echo "Could not determine one or more published compose ports." >&2
		return 1
	}
	export PCG_HTTP_PORT="${api_port##*:}"
	export NEO4J_BOLT_PORT="${neo4j_port##*:}"
	export JAEGER_PORT="${jaeger_port##*:}"
	refresh_runtime_endpoints "$PCG_HTTP_PORT" "$NEO4J_BOLT_PORT" "$JAEGER_PORT"
}
api_get() {
	local path="$1" output_file="$2"
	if [[ -n "$API_KEY" ]]; then
		curl -fsS -H "Authorization: Bearer $API_KEY" "$API_BASE_URL$path" >"$output_file"
	else
		curl -fsS "$API_BASE_URL$path" >"$output_file"
	fi
}
assert_json_query() {
	local file="$1" query="$2" description="$3"
	jq -e "$query" "$file" >/dev/null || {
		echo "$description" >&2
		cat "$file" >&2
		return 1
	}
}
require_fixture_file() {
	[[ -f "$1" ]] || {
		echo "Missing fixture file for $2: $1" >&2
		return 1
	}
}
require_fixture_match() {
	rg -q "$2" "$1" || {
		echo "Fixture assertion failed for $3: pattern [$2] not found in $1" >&2
		return 1
	}
}
repository_id_by_name() {
	jq -r --arg repo_name "$1" '
		def repo_rows:
			if type == "array" then .[]
			elif ((.repositories? // []) | length > 0) then .repositories[]
			elif ((.items? // []) | length > 0) then .items[]
			else empty end;
		first(repo_rows | select((.name // "") == $repo_name) | (.repo_id // .id // .repository_id // empty))
	' "$REPOSITORIES_FILE"
}
repo_names_json() {
	jq -c '
		def repo_names:
			if type == "array" then [.[].name]
			elif ((.repositories? // []) | length > 0) then [.repositories[].name]
			elif ((.items? // []) | length > 0) then [.items[].name]
			else [] end;
		repo_names | sort
	' "$1"
}
fetch_repo_context() {
	local repo_name="$1" repo_id
	repo_id="$(repository_id_by_name "$repo_name")"
	[[ -n "$repo_id" && "$repo_id" != "null" ]] || {
		echo "Could not resolve repository id for $repo_name from /repositories payload." >&2
		return 1
	}
	api_get "/repositories/${repo_id}/context" "$CONTEXT_FILE"
}
verify_fixture_corpus() {
	local service_path shared_path
	service_path="$CORRELATION_FIXTURE_ROOT/deploy-repo/argocd/service-gha/base/application.yaml"
	shared_path="$CORRELATION_FIXTURE_ROOT/deploy-repo/argocd/shared-config/base/configmap.yaml"
	require_fixture_file "$CORRELATION_FIXTURE_ROOT/service-gha/.github/workflows/deploy.yml" "service-gha workflow"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/service-gha/.github/workflows/deploy.yml" 'repository:[[:space:]]+deploy-repo' "service-gha deploy-repo checkout"
	require_fixture_file "$CORRELATION_FIXTURE_ROOT/service-jenkins/Jenkinsfile" "service-jenkins Jenkinsfile"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/service-jenkins/Jenkinsfile" 'terraform-stack-jenkins' "service-jenkins terraform reference"
	require_fixture_file "$CORRELATION_FIXTURE_ROOT/service-jenkins-ansible/Jenkinsfile" "service-jenkins-ansible Jenkinsfile"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/service-jenkins-ansible/Jenkinsfile" 'ansible-playbook[[:space:]]+playbooks/deploy.yml' "service-jenkins-ansible playbook handoff"
	require_fixture_file "$CORRELATION_FIXTURE_ROOT/service-compose/docker-compose.yaml" "service-compose compose file"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/service-compose/docker-compose.yaml" '^services:' "service-compose services block"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/service-compose/docker-compose.yaml" 'image:[[:space:]]+postgres:16' "service-compose database image"
	require_fixture_file "$service_path" "deploy-repo service application"
	require_fixture_file "$shared_path" "deploy-repo shared config"
	require_fixture_match "$service_path" 'kind:[[:space:]]+Application' "deploy-repo application kind"
	require_fixture_match "$service_path" 'repoURL:[[:space:]]+https://github.com/example/service-gha.git' "deploy-repo repoURL"
	require_fixture_match "$shared_path" 'kind:[[:space:]]+ConfigMap' "deploy-repo shared config kind"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/terraform-stack-gha/shared/main.tf" 'app_name[[:space:]]*=[[:space:]]*"service-gha"' "terraform-stack-gha app name"
	require_fixture_match "$CORRELATION_FIXTURE_ROOT/terraform-stack-jenkins/shared/main.tf" 'app_name[[:space:]]*=[[:space:]]*"service-jenkins"' "terraform-stack-jenkins app name"
	require_fixture_file "$CORRELATION_FIXTURE_ROOT/multi-dockerfile-repo/Dockerfile.test" "multi-dockerfile utility image"
}
verify_repository_selection() {
	api_get "/repositories" "$REPOSITORIES_FILE"
	local actual
	actual="$(repo_names_json "$REPOSITORIES_FILE")"
	[[ "$actual" == "$EXPECTED_REPOSITORIES_JSON" ]] || {
		echo "Repository selection mismatch. expected=$EXPECTED_REPOSITORIES_JSON actual=$actual" >&2
		return 1
	}
}
verify_service_gha_context() {
	fetch_repo_context "service-gha"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "service-gha" and
		((.infrastructure_overview.artifact_family_counts.github_actions // 0) >= 1) and
		((.infrastructure_overview.artifact_family_counts.docker // 0) >= 1) and
		((.deployment_artifacts.workflow_artifacts // []) | any(
			(.relative_path // "") == ".github/workflows/deploy.yml" and
			(.workflow_name // "") == "deploy"
		)) and
		((.deployment_artifacts.deployment_artifacts // []) | any(
			(.artifact_type // "") == "dockerfile" and
			(.relative_path // "") == "Dockerfile"
		))
	' "service-gha context missing expected GitHub Actions or Dockerfile signals"
}
verify_service_jenkins_context() {
	fetch_repo_context "service-jenkins"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "service-jenkins" and
		((.infrastructure_overview.artifact_family_counts.docker // 0) >= 1) and
		((.deployment_artifacts.controller_artifacts // []) | any(
			(.path // "") == "Jenkinsfile" and
			(.controller_kind // "") == "jenkins_pipeline"
		)) and
		((.deployment_artifacts.deployment_artifacts // []) | any(
			(.artifact_type // "") == "dockerfile" and
			(.relative_path // "") == "Dockerfile"
		))
	' "service-jenkins context missing expected Jenkins or Dockerfile signals"
}
verify_service_jenkins_ansible_context() {
	fetch_repo_context "service-jenkins-ansible"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "service-jenkins-ansible" and
		((.infrastructure_overview.artifact_family_counts.ansible // 0) >= 4) and
		((.deployment_artifacts.controller_artifacts // []) | any(
			(.path // "") == "Jenkinsfile" and
			(.controller_kind // "") == "jenkins_pipeline" and
			((.ansible_playbook_hints // []) | any((.playbook // "") == "playbooks/deploy.yml"))
		))
	' "service-jenkins-ansible context missing expected Jenkins plus Ansible signals"
}
verify_service_compose_context() {
	fetch_repo_context "service-compose"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "service-compose" and
		((.infrastructure_overview.artifact_family_counts.docker // 0) >= 1) and
		((.deployment_artifacts.deployment_artifacts // []) | any(
			(.artifact_type // "") == "docker_compose" and
			(.relative_path // "") == "docker-compose.yaml" and
			(.service_name // "") == "api" and
			((.signals // []) | index("build")) and
			((.ports // []) | index("8080:8080"))
		)) and
		((.deployment_artifacts.deployment_artifacts // []) | any(
			(.artifact_type // "") == "docker_compose" and
			(.service_name // "") == "database" and
			((.ports // []) | index("5432:5432"))
		))
	' "service-compose context missing expected Docker Compose runtime signals"
}
verify_terraform_contexts() {
	fetch_repo_context "terraform-stack-gha"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "terraform-stack-gha" and
		((.infrastructure_overview.entity_family_counts.terraform // 0) >= 1) and
		((.infrastructure_overview.families // []) | index("terraform"))
	' "terraform-stack-gha context missing Terraform entity-family coverage"
	fetch_repo_context "terraform-stack-jenkins"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "terraform-stack-jenkins" and
		((.infrastructure_overview.entity_family_counts.terraform // 0) >= 1) and
		((.infrastructure_overview.families // []) | index("terraform"))
	' "terraform-stack-jenkins context missing Terraform entity-family coverage"
}
verify_multi_dockerfile_context() {
	fetch_repo_context "multi-dockerfile-repo"
	assert_json_query "$CONTEXT_FILE" '
		(.repository.name // "") == "multi-dockerfile-repo" and
		((.infrastructure_overview.artifact_family_counts.docker // 0) >= 2) and
		((.deployment_artifacts.deployment_artifacts // []) | any(
			(.artifact_type // "") == "dockerfile" and
			(.relative_path // "") == "Dockerfile"
		)) and
		((.deployment_artifacts.deployment_artifacts // []) | any(
			(.artifact_type // "") == "dockerfile" and
			(.relative_path // "") == "Dockerfile.test"
		))
	' "multi-dockerfile-repo context missing both Dockerfile artifacts"
}
capture_resolution_metrics() {
	local attempts=15 sleep_seconds=2 metrics_url="http://localhost:${PCG_RESOLUTION_ENGINE_METRICS_PORT}/metrics"
	for ((attempt = 1; attempt <= attempts; attempt++)); do
		if curl -fsS "$metrics_url" >"$RESOLUTION_METRICS_FILE" 2>/dev/null; then
			if rg -q '^(pcg_dp_|pcg_runtime_)' "$RESOLUTION_METRICS_FILE"; then
				return 0
			fi
			echo "Resolution-engine metrics did not include pcg_dp_ or pcg_runtime_ signals; keeping capture for diagnosis."
			return 0
		fi
		/bin/sleep "$sleep_seconds"
	done
	: >"$RESOLUTION_METRICS_FILE"
	echo "Resolution-engine metrics endpoint was not ready at $metrics_url; continuing with placeholder capture."
	return 0
}
verify_graph_state() {
	local result
	result="$("${COMPOSE_CMD[@]}" exec -T neo4j cypher-shell \
		-u neo4j \
		-p "${PCG_NEO4J_PASSWORD:-change-me}" \
		--format plain \
		"MATCH (n:Repository) RETURN count(n) AS count")"
	result="$(printf '%s\n' "$result" | tail -n 1)"
	[[ "$result" == "$EXPECTED_REPO_COUNT" ]] || {
		echo "Expected $EXPECTED_REPO_COUNT Repository nodes in Neo4j, got: $result" >&2
		return 1
	}
}
log_api_key_mode() {
	if [[ -n "$API_KEY" ]]; then
		echo "Found PCG_API_KEY in the API container environment."
	else
		echo "No PCG_API_KEY is set in the API container; using unauthenticated local API access."
	fi
}
run_context_verifications() {
	echo "Verifying explicit repository selection and generic corpus contexts..."
	run_verification_step "repository selection" verify_repository_selection
	run_verification_step "service-gha context" verify_service_gha_context
	run_verification_step "service-jenkins context" verify_service_jenkins_context
	run_verification_step "service-jenkins-ansible context" verify_service_jenkins_ansible_context
	run_verification_step "service-compose context" verify_service_compose_context
	run_verification_step "terraform contexts" verify_terraform_contexts
	run_verification_step "multi-dockerfile context" verify_multi_dockerfile_context
	run_verification_step "graph state" verify_graph_state
	run_verification_step "resolution-engine metrics" capture_resolution_metrics
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
export COMPOSE_PROJECT_NAME
if [[ -z "${PCG_FILESYSTEM_HOST_ROOT:-}" ]]; then
	export PCG_FILESYSTEM_HOST_ROOT="$CORRELATION_FIXTURE_ROOT"
fi
export PCG_FILESYSTEM_HOST_ROOT="$(require_real_directory "$PCG_FILESYSTEM_HOST_ROOT")"
collect_fixture_repositories "$PCG_FILESYSTEM_HOST_ROOT"
export PCG_REPOSITORY_RULES_JSON="$(build_correlation_repo_rules_json)"
run_verification_step "fixture corpus shape" verify_fixture_corpus
"${COMPOSE_CMD[@]}" down -v >/dev/null 2>&1 || true
compose_started=false
for attempt in 1 2; do
	configure_ports
	echo "Starting local compose stack..."
	echo "Using host ports: api=$PCG_HTTP_PORT postgres=$PCG_POSTGRES_PORT neo4j_bolt=$NEO4J_BOLT_PORT jaeger=$JAEGER_UI_PORT"
	echo "Using compose project: $COMPOSE_PROJECT_NAME"
	echo "Using fixture root: $PCG_FILESYSTEM_HOST_ROOT"
	echo "Using repositories: ${FIXTURE_REPO_NAMES[*]}"
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
	/bin/sleep 2
done
[[ "$compose_started" == "true" ]] || {
	echo "Could not start the local compose stack after retrying." >&2
	exit 1
}
refresh_compose_ports
echo "Waiting for bootstrap indexing to finish..."
wait_for_bootstrap_exit 600
echo "Waiting for API health..."
wait_for_http "http://localhost:${API_PORT}/health" 60 2
echo "Reading API bearer token from the running API container..."
API_KEY="$(read_api_key)"
log_api_key_mode
echo "Waiting for /index-status queue completion..."
wait_for_index_completion 180 5
run_context_verifications
echo "Correlation DSL compose verification passed."
echo "API: $API_BASE_URL"
echo "Jaeger UI: $JAEGER_URL"
echo "Stack teardown: $COMPOSE_DISPLAY down -v"
exit 0
