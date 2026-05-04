# projector

## Purpose

`projector` is the local verification runtime for source-local
projection. It claims `projector` queue items from Postgres, runs the
projector runtime in `internal/projector/`, and writes canonical nodes
plus content store rows. In the deployed stack this work runs inside
`pcg-ingester`; this binary exists for focused local verification.

## Ownership boundary

The binary wires `projector.Service` and `projector.Runtime` around the
canonical writer, content writer, intent writer (the reducer queue),
phase publisher, and repair queue. It does not own collection
(`collector-git`/`ingester`), reducer-owned cross-domain materialization
(`pcg-reducer`), or graph schema DDL (`pcg-bootstrap-data-plane`).

## Entry points

- `main` and `run` in `go/cmd/projector/main.go`
- service wiring in `go/cmd/projector/runtime_wiring.go`
- retry helpers in `go/cmd/projector/config.go`

## Configuration

- `PCG_POSTGRES_DSN` and the standard Postgres env contract
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `DEFAULT_DATABASE`
  for the canonical writer (`runtime.OpenNeo4jDriver`)
- `PCG_NEO4J_BATCH_SIZE` (`neo4jBatchSize`) — `0` defers to the package
  default
- `PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION` — fault-injection knob
- retry policy via `runtime.LoadRetryPolicyConfig(getenv, "PROJECTOR")`
- content writer entity batch size via `content.LoadWriterConfig`

## Telemetry

Uses `telemetry.NewBootstrap("projector")`, `NewProviders`,
`NewInstruments`. Logger scope `projector`/component `projector`.
Canonical writes go through `storage/cypher.InstrumentedExecutor`. The
shared `/metrics`, `/healthz`, `/readyz`, `/admin/status` admin surface
is mounted by `app.NewHostedWithStatusServer`; see
`internal/runtime/README.md` and `internal/storage/cypher/README.md`.

## Gotchas / invariants

- claims come from `projector` queue rows; intents go to the `reducer`
  queue handle so `pcg-reducer` can pick them up
- the projector lease duration is one minute; long Neo4j writes that
  exceed that without heartbeat risk re-claim
- `SemanticEntityClaimLimit` and grouped writes are reducer-side
  concerns; this binary writes canonical nodes only
- shutdown is signal-driven (`SIGINT`/`SIGTERM`)

## Related docs

- [Service runtimes — Local Verification Runtimes](../../../docs/docs/deployment/service-runtimes.md#local-verification-runtimes)
- [CLI reference](../../../docs/docs/reference/cli-reference.md)
- [Docker Compose deployment](../../../docs/docs/deployment/docker-compose.md)
