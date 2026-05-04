# bootstrap-index

## Purpose

`pcg-bootstrap-index` is the one-shot operator helper for seeding an
empty or recovered PCG environment. It runs the multi-pass facts-first
pipeline: collection with first-pass projection, deferred
relationship-evidence backfill, IaC reachability materialization, and
the deployment-mapping reopen pass.

## Ownership boundary

This binary orchestrates collector and projector deps from
`internal/collector/` and `internal/projector/`. Reducer-owned
materialization runs in `pcg-reducer`; this binary triggers the
post-collection backfill, reachability materialization, and reopen
calls exposed on the collector committer.

## Entry points

- `main`, `run`, `runPipelined` in `go/cmd/bootstrap-index/main.go`
- collector / projector wiring in `go/cmd/bootstrap-index/wiring.go`
- NornicDB-specific wiring in
  `go/cmd/bootstrap-index/nornicdb_wiring.go`

## Configuration

- `PCG_PROJECTION_WORKERS` — default `min(NumCPU, 8)`
- `PCG_DISCOVERY_REPORT` — file path for collector advisory JSON
- `PCG_POSTGRES_DSN`, `PCG_GRAPH_BACKEND`, `NEO4J_URI`,
  `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `DEFAULT_DATABASE`,
  `PCG_NEO4J_BATCH_SIZE` and the collector / projector tuning knobs go
  through `runtime.OpenPostgres` and the shared wiring helpers

## Telemetry

Uses `telemetry.NewBootstrap("bootstrap-index")`, `NewProviders`,
`NewInstruments`. Logger scope `collector`/component `bootstrap-index`.
Spans: `SpanCollectorObserve`, `SpanProjectorRun`. Metrics: `FactsEmitted`,
`FactsCommitted`, `CollectorObserveDuration`, `QueueClaimDuration`
(`queue=projector`), `ProjectorRunDuration`, `ProjectionsCompleted`,
`PipelineOverlapDuration`. Failure-class log keys: `commit_failure`,
`backfill_deferred_failure`, `iac_reachability_materialization_failure`,
`reopen_deployment_mapping_failure`, `projection_failure`,
`lease_heartbeat_failure`. `GOMEMLIMIT` via `RecordGOMEMLIMIT`.

## Gotchas / invariants

- no shared `/metrics` HTTP surface; OTEL export is the only telemetry
- collector and projector run concurrently against a Postgres
  `FOR UPDATE SKIP LOCKED` queue; the projector drains after collection
- ordering follows the facts-first pipeline in CLAUDE.md; the
  deployment-mapping reopen replays succeeded items only
- a heartbeat goroutine renews the projector lease across long writes

## Related docs

- [Service runtimes — Bootstrap Index](../../../docs/docs/deployment/service-runtimes.md#bootstrap-index)
- [Docker Compose deployment](../../../docs/docs/deployment/docker-compose.md)
- [Bootstrap relationship backfill ADR](../../../docs/docs/adrs/2026-04-18-bootstrap-relationship-backfill-quadratic-cost.md)
