# Docker Compose

The repository includes a Docker Compose stack that mirrors the deployable-service lifecycle:

1. start Neo4j
2. start local Postgres for the content store
3. start a local OpenTelemetry collector
4. start Jaeger for trace inspection
5. bootstrap index fixture repos
6. start the HTTP API + MCP service
7. run the ingester service, which keeps the repo-sync loop running in the background
8. run the standalone resolution-engine loop

Compose files:
- `docker-compose.yaml`
- `docker-compose.template.yml`

Run it with:

```bash
docker compose up --build
```

For the exact verification matrix around Compose, package tests, and docs
checks, use the [Local Testing Runbook](../reference/local-testing.md).

Before you start the stack against host repositories, confirm that
`PCG_FILESYSTEM_HOST_ROOT` points at an absolute real directory. Do not use a
symlinked path, and do not use macOS `/tmp` because Docker resolves it through
`/private/tmp`.

This stack cannot run a real Kubernetes `ServiceMonitor`, but it can run the
same thing a `ServiceMonitor` would scrape:

- a Prometheus-format `/metrics` endpoint on `platform-context-graph`
- a Prometheus-format `/metrics` endpoint on `ingester`
- a Prometheus-format `/metrics` endpoint on `resolution-engine`

Those endpoints carry the current Go metric split:

- `pcg_dp_*` for data-plane counters, histograms, and gauges
- `pcg_runtime_*` for runtime health and queue state

For the admin re-finalize flow specifically, use the compose-backed verification
wrapper:

```bash
./scripts/verify_admin_refinalize_compose.sh
```

That script:
- starts the local compose stack from a clean state
- waits for bootstrap indexing plus API and ingester health
- selects a live scope from the compose Postgres state
- calls the ingester `/admin/refinalize` endpoint from inside the
  compose network
- captures the before/after admin status payload when the flow fails
- prints the Jaeger URL, selected `scope_id`, and useful logs for debugging
- auto-selects free host ports when the usual local defaults are already occupied

The runtime verification wrappers under `scripts/verify_*_compose.sh` are
shell-native Go-runtime checks.

Run one wrapper at a time. They share the same Compose project name, so
parallel wrapper runs can collide even when each script chooses different host
ports.

Set `PCG_KEEP_COMPOSE_STACK=true` if you want the stack left running after the verification completes.

By default, the bootstrap, ingester, and resolution-engine services mount the fixture ecosystems tree from
`./tests/fixtures/ecosystems` into `/fixtures` so the stack stays safe for local smoke testing.

The runtime services export OTLP traces and metrics to the local collector by default, and the
collector forwards traces into Jaeger. Open `http://localhost:16686` after the stack starts to
inspect spans. The collector also exposes Prometheus-format metrics on
`http://localhost:9464/metrics` by default, so local OTLP metric export has a real sink instead of
failing with `UNIMPLEMENTED`.

Local auth stays at the Go API boundary too:

- `PCG_API_KEY` is the bearer token contract when local auth is enabled.
- If `PCG_API_KEY` is not passed into Compose, the Go runtime can reuse a persisted token from
  `PCG_HOME/.env` or generate and persist one when `PCG_AUTO_GENERATE_API_KEY=true`.
- The compose verification scripts check both the running container environment and the persisted
  `PCG_HOME/.env` contract before issuing authenticated requests.
- If neither source contains a token, the local stack runs without bearer auth.
- There is no separate auth service, login flow, or OAuth dependency in this stack.

For direct runtime scraping, Compose also enables per-runtime Prometheus endpoints:

- API: `http://localhost:19464/metrics`
- Ingester: `http://localhost:19465/metrics`
- Resolution Engine: `http://localhost:19466/metrics`

Those defaults are configurable through:

- `PCG_API_METRICS_PORT`
- `PCG_INGESTER_METRICS_PORT`
- `PCG_RESOLUTION_ENGINE_METRICS_PORT`

## Local Metrics Checks

To verify the endpoints manually:

```bash
curl http://localhost:19464/metrics | head
curl http://localhost:19465/metrics | head
curl http://localhost:19466/metrics | head
```

To watch one runtime live:

```bash
watch -n 2 'curl -fsS http://localhost:19466/metrics | rg "^(pcg_dp_|pcg_runtime_)" | head -40'
```

To see live counters change while you exercise the stack, open two terminals:

```bash
watch -n 2 'curl -fsS http://localhost:19464/metrics | rg "^(pcg_dp_|pcg_runtime_)" | head -40'
```

```bash
watch -n 2 'curl -fsS http://localhost:19465/metrics | rg "^(pcg_dp_|pcg_runtime_)" | head -40'
```

```bash
watch -n 2 'curl -fsS http://localhost:19466/metrics | rg "^(pcg_dp_|pcg_runtime_)" | head -60'
```

The canonical Compose assets honor the current worker-tuning controls from the
environment:

- `PCG_PROJECTION_WORKERS`
- `PCG_SNAPSHOT_WORKERS`
- `PCG_PARSE_WORKERS`
- `PCG_PROJECTOR_WORKERS`
- `PCG_REDUCER_WORKERS`
- `PCG_SHARED_PROJECTION_WORKERS`
- `PCG_SHARED_PROJECTION_PARTITION_COUNT`
- `PCG_SHARED_PROJECTION_BATCH_LIMIT`
- `PCG_SHARED_PROJECTION_POLL_INTERVAL`
- `PCG_SHARED_PROJECTION_LEASE_TTL`
- `PCG_LARGE_REPO_FILE_THRESHOLD`
- `PCG_LARGE_REPO_MAX_CONCURRENT`

Compose passes the Go controls through to `bootstrap-index`, `ingester`,
`resolution-engine`, and `platform-context-graph`, so local and containerized
runs stay aligned with the Go runtime/data-plane stack.

Health and completeness are separate checks in Compose, too:

- `curl -fsS http://localhost:8080/health` confirms the API process is alive
- `curl -fsS http://localhost:8080/api/v0/index-status` reports the latest
  checkpointed indexing completeness summary
- `curl -fsS http://localhost:8080/api/v0/repositories/<repo_id>/coverage`
  reports repository-specific coverage detail

For a real local end-to-end run against a host directory, override the host-side
source root with an absolute path:

```bash
PCG_FILESYSTEM_HOST_ROOT="$HOME/repos/example-org" \
docker compose up --build
```

Use an absolute host path for `PCG_FILESYSTEM_HOST_ROOT`; do not rely on a
literal `~` in Compose environment values.

If you need a disposable workspace copy for Compose, create a real directory
such as `$HOME/tmp/pcg-compose-repos` rather than a symlinked scratch path.

When Docker runs through Colima, prefer a host path under your home directory
such as `$HOME/temp-repos-mount` or `$HOME/repos/example-org`. Colima does not
reliably expose arbitrary `/tmp` content into the Linux VM, so a source tree
copied to `/tmp/temp-repos` on macOS can appear empty inside the Compose
containers even though the bind mount renders successfully.

If you already have Neo4j or another copy of PlatformContextGraph bound to the default local ports,
override the published host ports:

```bash
NEO4J_HTTP_PORT=17474 \
NEO4J_BOLT_PORT=17687 \
PCG_POSTGRES_PORT=15432 \
PCG_HTTP_PORT=18080 \
JAEGER_UI_PORT=26686 \
OTEL_COLLECTOR_OTLP_GRPC_PORT=24317 \
OTEL_COLLECTOR_PROMETHEUS_PORT=29464 \
PCG_API_METRICS_PORT=21464 \
PCG_INGESTER_METRICS_PORT=21465 \
PCG_RESOLUTION_ENGINE_METRICS_PORT=21466 \
docker compose up --build
```

This stack is intended for:
- local integration testing
- API and MCP smoke testing
- validating fixture-driven indexing flows
- live trace inspection through the bundled Jaeger UI
- live OTEL metric inspection through the collector Prometheus endpoint
- live direct runtime scrape inspection with `curl` or `watch`
- exercising indexing worker controls in the same environment shape used by CI

It also exercises the content-store contract:

- `PCG_CONTENT_STORE_DSN` and `PCG_POSTGRES_DSN` are wired by default
- host-side e2e runs can reach the bundled Postgres content store through `PCG_POSTGRES_PORT` (default `15432`)
- file and entity content reads prefer Postgres and fall back to the server workspace
- `PCG_REPOSITORY_RULES_JSON` can be set to structured exact or regex include rules for Git-backed sync, and Compose passes that override through to every Go runtime in the stack
- compose-backed relationship verification relies on Go-written repo-edge
  `evidence_type` metadata so API repository contexts can classify
  controller-, workflow-, and IaC-driven relationships without any Python
  read-path enrichment
- the bundled local Postgres enables `pg_trgm` automatically through the content-store schema bootstrap
- `OTEL_EXPORTER_OTLP_ENDPOINT` points at `http://otel-collector:4317` inside the Compose network
- the local collector config lives at `deploy/observability/otel-collector-config.yaml`
