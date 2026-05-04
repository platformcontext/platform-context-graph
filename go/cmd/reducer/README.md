# reducer

## Purpose

`pcg-reducer` is the resolution-engine runtime: it claims items from
the reducer fact-work queue, runs domain handlers, materializes
cross-domain truth (deployable-unit correlation, workload identity,
infrastructure platform, semantic entities, code-call edges,
repo-dependency edges), and drives graph-projection-phase repair.
The deployed service identity is `resolution-engine`.

## Ownership boundary

Domain logic lives in `internal/reducer/`; graph-write contracts live
in `internal/storage/cypher/`. This binary wires the service plus the
shared-projection, code-call, repo-dependency, and repair runners. It
does not own repo sync, parsing, fact emission (`ingester`),
source-local canonical projection, or HTTP read traffic.

## Entry points

- `main`, `run`, `buildReducerService` in `go/cmd/reducer/main.go`
- Neo4j wiring in `go/cmd/reducer/neo4j_wiring.go`
- workload-dependency lookup and config helpers in
  `go/cmd/reducer/workload_dependency_lookup.go` and `config.go`

## Configuration

Defined in `go/cmd/reducer/config.go`:

- queue + retry: `PCG_REDUCER_RETRY_DELAY`, `PCG_REDUCER_MAX_ATTEMPTS`,
  `PCG_REDUCER_BATCH_CLAIM_SIZE`, `PCG_REDUCER_CLAIM_DOMAIN`,
  `PCG_REDUCER_WORKERS` (default `min(NumCPU, 8)` on NornicDB,
  `min(NumCPU, 4)` on Neo4j)
- gating: `PCG_REDUCER_EXPECTED_SOURCE_LOCAL_PROJECTORS`,
  `PCG_REDUCER_SEMANTIC_ENTITY_CLAIM_LIMIT`; `PCG_QUERY_PROFILE` with
  `PCG_GRAPH_BACKEND=nornicdb` enables the projector drain gate
- shared projection: `PCG_CODE_CALL_PROJECTION_*` and
  `PCG_REPO_DEPENDENCY_PROJECTION_*` (`POLL_INTERVAL`, `LEASE_TTL`,
  `BATCH_LIMIT`, `LEASE_OWNER`; code-call also has
  `ACCEPTANCE_SCAN_LIMIT`)
- edge writers: `PCG_CODE_CALL_EDGE_BATCH_SIZE`,
  `PCG_CODE_CALL_EDGE_GROUP_BATCH_SIZE`,
  `PCG_INHERITANCE_EDGE_GROUP_BATCH_SIZE`,
  `PCG_SQL_RELATIONSHIP_EDGE_GROUP_BATCH_SIZE`, `PCG_NEO4J_BATCH_SIZE`
- repair: `PCG_GRAPH_PROJECTION_REPAIR_POLL_INTERVAL`,
  `..._BATCH_LIMIT`, `..._RETRY_DELAY`
- `PCG_GRAPH_BACKEND` plus the NornicDB grouped-write and timeout knobs

## Telemetry

Uses `telemetry.NewBootstrap("reducer")`, `NewProviders`,
`NewInstruments`. Logger scope `reducer`/component `reducer`. Postgres
queries go through `postgres.InstrumentedDB{StoreName: "reducer"}`;
Cypher executes through `storage/cypher.InstrumentedExecutor`. Queue
depth via `postgres.NewQueueObserverStore`. The shared `/metrics`,
`/healthz`, `/readyz`, `/admin/status` admin surface is mounted by
`app.NewHostedWithStatusServer`; see `internal/runtime/README.md` and
`internal/storage/cypher/README.md`.

## Gotchas / invariants

- the projector drain gate is on only with
  `PCG_GRAPH_BACKEND=nornicdb` and `PCG_QUERY_PROFILE=local-authoritative`
- worker leases renew at `LeaseDuration / 2`; retry delay shorter than
  the lease TTL makes claims churn
- handlers depend on graph-projection readiness published by the projector

## Related docs

- [Service runtimes — Resolution Engine](../../../docs/docs/deployment/service-runtimes.md#resolution-engine)
- [NornicDB tuning](../../../docs/docs/reference/nornicdb-tuning.md)
- [Reducer full convergence ADR](../../../docs/docs/adrs/2026-04-18-reducer-full-convergence-optimization.md)
