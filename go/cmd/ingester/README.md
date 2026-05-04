# ingester

## Purpose

`pcg-ingester` is the long-running runtime that discovers and syncs
repositories, parses snapshots, emits facts into Postgres, and runs the
source-local projection that writes canonical nodes into the graph
backend. In Kubernetes it runs as a StatefulSet and is the only runtime
that mounts the shared workspace PVC.

## Ownership boundary

The ingester owns the collector + source-local projector pipeline plus
the runtime admin and recovery transport. Cross-domain materialization
lives in `pcg-reducer`; HTTP reads live in `pcg-api` / `pcg-mcp-server`;
schema DDL lives in `pcg-bootstrap-data-plane`. `collector-git` is the
local verification half of the same collector contract.

## Entry points

- `main`, `run` in `go/cmd/ingester/main.go`
- wiring in `go/cmd/ingester/wiring.go` and
  `go/cmd/ingester/wiring_nornicdb_*.go`
- retry / config helpers in `go/cmd/ingester/config.go`

## Configuration

- `PCG_POSTGRES_DSN` plus the standard Postgres env contract;
  `PCG_GRAPH_BACKEND`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`,
  `DEFAULT_DATABASE`
- `PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION` — fault-injection knob;
  retry policy via `runtime.LoadRetryPolicyConfig(getenv, "PROJECTOR")`
- `PCG_SNAPSHOT_WORKERS`, `PCG_NEO4J_BATCH_SIZE`, and the NornicDB
  knobs in `docs/docs/reference/nornicdb-tuning.md`

## Telemetry

Uses `telemetry.NewBootstrap("ingester")`, `NewProviders`,
`NewInstruments`. Logger scope `collector`/component `ingester`.
Postgres queries go through `postgres.InstrumentedDB{StoreName:
"ingester"}`; queue depth via `postgres.NewQueueObserverStore` and
`telemetry.RegisterObservableGauges`; `GOMEMLIMIT` via
`telemetry.RecordGOMEMLIMIT`. `/healthz`, `/readyz`, `/metrics`,
`/admin/status`, `/admin/recovery` are mounted by
`app.NewHostedWithStatusServer`; see `internal/runtime/README.md`.

## Gotchas / invariants

- StatefulSet only: Kubernetes runs one ingester per workspace PVC
- shutdown is signal-driven (`SIGINT`/`SIGTERM`)
- the retry-policy summary uses the `projector` stage label because
  source-local projection is the owning stage
- recovery routes mount only when API-key resolution succeeds; check
  `runtime.NewRecoveryHandler` if `/admin/recovery` is missing

## Related docs

- [Service runtimes — Ingester](../../../docs/docs/deployment/service-runtimes.md#ingester)
- [Docker Compose deployment](../../../docs/docs/deployment/docker-compose.md)
- [NornicDB tuning](../../../docs/docs/reference/nornicdb-tuning.md)
