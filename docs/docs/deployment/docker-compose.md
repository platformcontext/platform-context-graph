# Docker Compose

The repository includes a Docker Compose stack that mirrors the deployable-service lifecycle:

1. start Neo4j
2. start local Postgres for the content store
3. start a local OpenTelemetry collector
4. start Jaeger for trace inspection
5. bootstrap index fixture repos
6. start the combined HTTP API + MCP service
7. run an ongoing repo-sync loop

Compose files:
- `docker-compose.yaml`
- `docker-compose.template.yml`

Run it with:

```bash
docker compose up --build
```

By default, the bootstrap and repo-sync services mount the fixture ecosystems tree from
`./tests/fixtures/ecosystems` into `/fixtures` so the stack stays safe for local smoke testing.

The runtime services export OTLP traces and metrics to the local collector by default, and the
collector forwards traces into Jaeger. Open `http://localhost:16686` after the stack starts to
inspect spans. The collector also exposes Prometheus-format metrics on
`http://localhost:9464/metrics` by default, so local OTLP metric export has a real sink instead of
failing with `UNIMPLEMENTED`.

For a real local end-to-end run against a host directory, override the host-side source root with
an absolute path:

```bash
PCG_FILESYSTEM_HOST_ROOT="$HOME/repos/mobius" \
docker compose up --build
```

Use an absolute host path for `PCG_FILESYSTEM_HOST_ROOT`; do not rely on a literal `~` in Compose
environment values.

If you already have Neo4j or another copy of PlatformContextGraph bound to the default local ports,
override the published host ports:

```bash
NEO4J_HTTP_PORT=17474 \
NEO4J_BOLT_PORT=17687 \
PCG_HTTP_PORT=18080 \
JAEGER_UI_PORT=26686 \
OTEL_COLLECTOR_OTLP_GRPC_PORT=24317 \
OTEL_COLLECTOR_PROMETHEUS_PORT=29464 \
docker compose up --build
```

This stack is intended for:
- local integration testing
- API and MCP smoke testing
- validating fixture-driven indexing flows
- live trace inspection through the bundled Jaeger UI
- live OTEL metric inspection through the collector Prometheus endpoint

It also exercises the content-store contract:

- `PCG_CONTENT_STORE_DSN` and `PCG_POSTGRES_DSN` are wired by default
- file and entity content reads prefer Postgres and fall back to the server workspace
- `PCG_REPOSITORY_RULES_JSON` can be set to structured exact or regex include rules for Git-backed sync
- the bundled local Postgres enables `pg_trgm` automatically through the content-store schema bootstrap
- `OTEL_EXPORTER_OTLP_ENDPOINT` points at `http://otel-collector:4317` inside the Compose network
- the local collector config lives at `deploy/observability/otel-collector-config.yaml`
