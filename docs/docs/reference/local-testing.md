# Local Testing Runbook

This is the default local verification runbook for engineers, Claude, and
Codex.

Use it to answer:

- which commands should I run for this kind of change
- what is the minimum acceptable verification before I call work ready
- how do I run the local full-stack workflow
- how do I validate metrics, traces, and the facts-first pipeline

## Default Rule

Run the smallest test set that proves the change, then run the deployment and
docs checks required by the surfaces you touched.

Do not call a change ready without citing the commands you actually ran.

## Common Environment

When running directly against a local Docker Compose stack:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src
```

## Quick Verification Matrix

| If you touched | Minimum verification |
| --- | --- |
| Docs, `CLAUDE.md`, `AGENTS.md`, or README files | `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml` |
| CLI/runtime wiring | `PYTHONPATH=src uv run pytest tests/integration/cli/test_cli_commands.py -q` |
| Compose, Helm, or deployable runtime shape | `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q` and `helm lint deploy/helm/platform-context-graph` |
| Facts-first indexing, queue, or resolution flow | `PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_git_facts_end_to_end.py tests/integration/indexing/test_git_facts_projection_parity.py -q` |
| Phase 3 recovery controls | `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_recovery.py tests/unit/api/test_admin_facts_recovery_router.py tests/integration/cli/test_remote_cli.py -q` |
| Facts-first telemetry or queue scaling | `PYTHONPATH=src:. uv run pytest tests/unit/observability/test_fact_resolution_telemetry.py tests/unit/observability/test_fact_runtime_scaling_telemetry.py tests/unit/observability/test_resolution_queue_sampler.py tests/unit/observability/test_facts_first_logging.py -q` |
| Admin replay flow | `PYTHONPATH=src uv run pytest tests/integration/api/test_admin_facts_replay.py tests/integration/cli/test_admin_facts_replay_cli.py -q` |
| Python file layout/quality gates | `python3 scripts/check_python_file_lengths.py --max-lines 500` and `git diff --check` |

## Go Data Plane Milestone 1 Gate

Use this gate when validating the bounded Go rewrite proof path for Milestone 1.

Current bounded proof path:

- `collector-git` owns cycle orchestration and durable fact commit
- `projector` owns source-local graph and content materialization
- `reducer` owns workload-identity follow-up drain
- all three runtimes expose `/healthz`, `/readyz`, `/metrics`, and
  `/admin/status`

Focused Go package gate:

```bash
cd go
go test ./internal/collector ./internal/compatibility/pythonbridge ./cmd/collector-git \
  ./internal/runtime ./internal/app ./internal/telemetry \
  ./internal/storage/neo4j ./internal/storage/postgres \
  ./internal/reducer ./cmd/reducer -count=1
```

Focused Python bridge gate:

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/compatibility/test_go_collector_selection_bridge.py \
  tests/unit/compatibility/test_go_collector_snapshot_bridge.py -q
```

Live runtime proof gate:

```bash
./scripts/verify_collector_git_runtime_compose.sh
./scripts/verify_projector_runtime_compose.sh
./scripts/verify_reducer_runtime_compose.sh
./scripts/verify_incremental_refresh_compose.sh
```

These proof scripts allocate their own local ports, start only the required
compose-backed infrastructure, and tear the stack down automatically unless
`PCG_KEEP_COMPOSE_STACK=true` is set.

## Go Data Plane Proof Domain Gate

Use this narrower proof-domain gate when you only need to validate the
collector-to-projector-to-reducer workload-identity path without rerunning all
three runtime proof scripts.

Current proof domain: `workload_identity`

```bash
cd go
go test ./internal/storage/postgres -run TestProofDomainWorkloadIdentityFlowsCollectorToReducerIntent -count=1
```

This proves the deterministic path from a repo snapshot into facts, source-local
projection, and reducer-intent enqueue/drain.

## Go Data Plane Milestone 2 Gate

Use this gate when validating the stronger scope-first incremental refresh
proof. It keeps the same compose shape but now expects three phases:

- one active generation at the start
- an unchanged rerun that leaves the authoritative generation and projector
  queue unchanged
- a changed rerun that reappears as `retrying` before the active/superseded
  swap completes

```bash
./scripts/verify_incremental_refresh_compose.sh
```

The current live blocker is the projector handoff ordering around the
`scope_generations_active_scope_idx` uniqueness check; if the changed rerun
cannot promote cleanly, the proof should fail and the proof log will show the
exact SQL error. If the runtime does not emit a retrying projector work item
for the changed rerun, keep that gap explicit in the proof output instead of
pretending the retry transition already exists.

## Local Full Stack

Start the full stack:

```bash
docker compose up --build
```

This brings up:

- Neo4j
- Postgres
- OTEL collector
- Jaeger
- `bootstrap-index`
- `platform-context-graph`
- `ingester`
- `resolution-engine`

Useful checks:

```bash
docker compose ps
docker compose logs bootstrap-index | tail -50
docker compose logs ingester | tail -50
docker compose logs resolution-engine | tail -50
curl -s http://localhost:8080/health
```

## Local Observability Checks

### Traces

- Jaeger UI: `http://localhost:16686`
- Collector Prometheus endpoint: `http://localhost:9464/metrics`

### Direct Runtime Metrics

Compose does not run a Kubernetes `ServiceMonitor`, but it does expose the same
runtime `/metrics` endpoints that a `ServiceMonitor` would scrape:

- API: `http://localhost:19464/metrics`
- Ingester: `http://localhost:19465/metrics`
- Resolution Engine: `http://localhost:19466/metrics`

Quick checks:

```bash
curl -fsS http://localhost:19464/metrics | head
curl -fsS http://localhost:19465/metrics | head
curl -fsS http://localhost:19466/metrics | head
```

Live watch examples:

```bash
watch -n 2 'curl -fsS http://localhost:19464/metrics | rg "^(pcg_http|pcg_mcp)" | head -40'
```

```bash
watch -n 2 'curl -fsS http://localhost:19466/metrics | rg "^(pcg_fact|pcg_resolution)" | head -60'
```

## Shared-Write Tuning Report

Use the local deterministic tuning report when you want a quick recommendation
before changing shared-write partition or batch settings in staging.

Readable table output:

```bash
PYTHONPATH=src:. uv run python scripts/shared_projection_tuning_report.py --format table
```

Machine-readable JSON output:

```bash
PYTHONPATH=src:. uv run python scripts/shared_projection_tuning_report.py --format json
```

To include platform shared-followup alongside dependency domains:

```bash
PYTHONPATH=src:. uv run python scripts/shared_projection_tuning_report.py --format table --include-platform
```

Use the report to pick a candidate setting, then validate that change in
staging with:

- `pcg_shared_projection_pending_intents`
- `pcg_shared_projection_oldest_pending_age_seconds`
- `pcg_fact_queue_depth`
- `pcg_fact_queue_oldest_age_seconds`

For deployed environments, `pcg workspace status --service-url ...` will also
surface the live `shared_projection_tuning` recommendation whenever shared
follow-up backlog is present.

## Data Intelligence Foundation Gate

Use this gate when a change touches the vendor-neutral data-intelligence core,
canonical data entity types, or SQL/data impact-query surfacing.

### Current branch coverage

The current foundation slice proves canonical data-native entity types,
resolution and impact-query support for `data_asset`, `data_column`,
`analytics_model`, `query_execution`, `dashboard_asset`, and
`data_quality_check`, plus replay-backed compiled SQL, BI, semantic,
quality, and governance lineage surfaces. It also covers the supported
compiled-SQL subset, explicit partial coverage reporting, graph/content
persistence registration for the new data entity families, and
persona-friendly context summaries that label declared versus observed
evidence.

### Fast foundation gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/query/test_entity_resolution.py \
  tests/unit/query/test_entity_context.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/data_intelligence/test_plugins.py -q
```

### SQL + data-query regression gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/parsers/test_sql_parser.py \
  tests/unit/parsers/test_python_sql_mappings.py \
  tests/unit/parsers/test_go_sql_extraction.py \
  tests/unit/relationships/test_sql_links.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/mcp/test_ecosystem_sql_blast_radius.py -q
```

### Compiled analytics replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_plugins.py \
  tests/unit/data_intelligence/test_dbt_compiled_sql.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/tools/test_graph_builder_schema.py -q
```

### Warehouse replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_plugins.py \
  tests/unit/data_intelligence/test_warehouse_replay.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py -q
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

### BI replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_bi_replay.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py -q
```
Use the same compose-backed integration smoke command as the warehouse replay gate.

### Semantic replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_semantic_replay.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py -q
```
Use the same compose-backed integration smoke command as the warehouse replay gate.

### Governance replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_governance_replay.py \
  tests/unit/parsers/test_json_governance_replay.py \
  tests/unit/content/test_data_intelligence_ingest.py \
  tests/unit/relationships/test_data_intelligence_governance_links.py \
  tests/unit/query/test_repository_context_data_governance.py \
  tests/unit/query/test_story_data_governance.py \
  tests/unit/tools/test_graph_builder_schema.py -q
```
Use the same compose-backed integration smoke command as the warehouse replay gate.

### Quality replay gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/data_intelligence/test_quality_replay.py \
  tests/unit/parsers/test_json_parser.py \
  tests/unit/content/test_ingest.py \
  tests/unit/relationships/test_data_intelligence_links.py \
  tests/unit/tools/test_graph_builder_schema.py \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py -q
```
Use the same compose-backed integration smoke command as the warehouse replay gate.

### Declared vs observed reconciliation gate

```bash
PYTHONPATH=src uv run pytest \
  tests/unit/query/test_repository_context_data_intelligence.py \
  tests/unit/query/test_story_data_intelligence.py \
  tests/unit/query/test_change_surface.py \
  tests/unit/query/test_entity_context.py \
  tests/unit/query/test_entity_resolution.py -q
```

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src

uv run pytest \
  tests/integration/test_sql_graph.py \
  tests/integration/test_warehouse_replay_graph.py \
  tests/integration/test_mcp_data_intelligence_queries.py -q
```

## Recommended Test Order

### 1. Run the smallest targeted test first

Start with the most local unit or integration suite that covers the files you
touched.

### 2. Verify the deployment contract if runtime shape changed

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q
helm lint deploy/helm/platform-context-graph
```

### 3. Verify facts-first parity if indexing changed

```bash
PYTHONPATH=src:. uv run pytest \
  tests/integration/indexing/test_git_facts_end_to_end.py \
  tests/integration/indexing/test_git_facts_projection_parity.py -q
```

### 4. Verify telemetry if observability changed

```bash
PYTHONPATH=src:. uv run pytest \
  tests/unit/observability/test_fact_resolution_telemetry.py \
  tests/unit/observability/test_fact_runtime_scaling_telemetry.py \
  tests/unit/observability/test_resolution_queue_sampler.py \
  tests/unit/observability/test_facts_first_logging.py -q
```

### 5. Verify recovery and admin controls if Phase 3 controls changed

```bash
PYTHONPATH=src:. uv run pytest \
  tests/unit/facts/test_fact_work_queue_recovery.py \
  tests/unit/api/test_admin_facts_recovery_router.py \
  tests/integration/cli/test_remote_cli.py -q
```

### 6. Build docs if docs or instruction files changed

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Full Local Smoke For Release Candidates

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q
PYTHONPATH=src uv run pytest tests/integration/cli/test_cli_commands.py -q
PYTHONPATH=src:. uv run pytest \
  tests/integration/indexing/test_git_facts_end_to_end.py \
  tests/integration/indexing/test_git_facts_projection_parity.py -q
PYTHONPATH=src:. uv run pytest \
  tests/unit/observability/test_fact_resolution_telemetry.py \
  tests/unit/observability/test_fact_runtime_scaling_telemetry.py \
  tests/unit/observability/test_resolution_queue_sampler.py \
  tests/unit/observability/test_facts_first_logging.py -q
PYTHONPATH=src:. uv run pytest \
  tests/unit/facts/test_fact_work_queue_recovery.py \
  tests/unit/api/test_admin_facts_recovery_router.py \
  tests/integration/cli/test_remote_cli.py -q
python3 scripts/check_python_file_lengths.py --max-lines 500
git diff --check
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## IaC Validation When The Deployment Repo Changes Too

If the app change requires updates in `iac-eks-pcg`, also run there:

```bash
helm lint chart/ \
  -f argocd/platformcontextgraph/base/app-values.yaml \
  -f argocd/platformcontextgraph/overlays/ops-qa/app-values.yaml

helm template platformcontextgraph chart/ \
  -f argocd/platformcontextgraph/base/app-values.yaml \
  -f argocd/platformcontextgraph/overlays/ops-qa/app-values.yaml >/tmp/pcg-chart.yaml

kubectl kustomize argocd/platformcontextgraph/overlays/ops-qa >/tmp/pcg-kustomize.yaml
```

## Completion Gate

Before Claude or Codex says a change is ready:

1. identify the changed surface area
2. run the matching checks from this page
3. report the exact commands run
4. report anything not run
5. do not substitute "looks correct" for verification output
