# Service Runtimes

Use this page when you need the operator view of PlatformContextGraph:

- which services exist
- what each service owns
- which command starts each service
- which service should be tuned or scaled
- where metrics are exposed
- where `ServiceMonitor` applies

Every long-running runtime should also follow one operator principle:

- the service should expose a familiar admin/status story through the shared
  report seam
- the same service should be inspectable through CLI now and API/admin
  transport once mounted
- the exact counters may differ by runtime, but the operator experience should
  not

That shared admin contract is used by the core data-plane services, including
MCP, that mount `go/internal/runtime`:

- `/healthz` and `/readyz` describe process health and readiness
- `/metrics` exposes runtime and backlog signals
- `/admin/status` renders the shared status/report shape
- the CLI and HTTP/admin views should render the same underlying report
- live-versus-inferred state must be explicit in both views

Current branch reality:

- the platform runtime is Go-owned end to end
- `collector-git`, `ingester`, and `bootstrap-index` own repository selection,
  repo sync, snapshot collection, parsing, content shaping, and fact emission
- local `pcg index`, `pcg workspace index`, `pcg watch`, and package indexing
  all hand off to Go binaries rather than a deleted Python coordinator path
- when `SCIP_INDEXER=true`, the collector owns SCIP language detection,
  external `scip-*` execution, protobuf reduction, and Go tree-sitter
  supplementation without Python delegation
- Terraform provider-schema assets are packaged and loaded from
  `go/internal/terraformschema/schemas/*.json.gz`
- Python no longer owns any deployed or long-running runtime on this branch
- the API, MCP, ingester, reducer, collector proof lane, and bootstrap helpers
  emit structured JSON logs through the shared Go telemetry logger

## Runtime Contract

| Runtime | Owns | Default command | Storage access | Metrics exposure | Kubernetes shape |
| --- | --- | --- | --- | --- | --- |
| DB Migrate | Postgres + Neo4j schema DDL | `/usr/local/bin/pcg-bootstrap-data-plane` | Postgres DDL + Neo4j DDL | none (exits immediately) | `initContainer` |
| API | HTTP API, query reads, admin endpoints | `pcg api start --host 0.0.0.0 --port 8080` | graph + content reads only | direct `/metrics`, optional `ServiceMonitor` | `Deployment` |
| MCP Server | MCP tool transport plus mounted query passthrough | `pcg mcp start` | graph + content reads only | direct `/metrics`, optional `ServiceMonitor` | `Deployment` |
| Ingester | repo sync, parsing, fact emission, workspace ownership | `/usr/local/bin/pcg-ingester` | workspace PVC + Postgres + Neo4j | direct `/metrics`, optional `ServiceMonitor` | `StatefulSet` |
| Resolution Engine | queue draining, projection, retries, replay, recovery | `/usr/local/bin/pcg-reducer` | Postgres + Neo4j | direct `/metrics`, optional `ServiceMonitor` | `Deployment` |
| Bootstrap Index | one-shot initial indexing | `/usr/local/bin/pcg-bootstrap-index` | workspace + Postgres + Neo4j | direct `/metrics` in Compose | one-shot local helper |

## Health, Status, And Completeness

- API, MCP, ingester, reducer, and other runtimes that mount
  `go/internal/runtime` use `/healthz`, `/readyz`, `/admin/status`, and
  `/metrics`.
- The MCP server also exposes `GET /health`, `GET /sse`, `POST /mcp/message`,
  and mounted `/api/*` routes for transport-specific behavior.
- Shared `/admin/status` reports the live runtime stage, backlog, and failure
  state where mounted.
- `GET /api/v0/status/index` is the normalized Go-owned completeness route.
- `GET /api/v0/index-status` is the legacy compatibility alias for the same
  completeness payload.
- `GET /api/v0/repositories/{repo_id}/coverage` narrows the completeness view
  to the repository rows that still need attention.
- Run-scoped completeness routes remain an open parity item on this branch.
- A service can be healthy while indexing is incomplete. Operators should use
  completeness routes before assuming a full run has finished.
- `bootstrap-index` remains a one-shot helper for empty or recovered
  environments, not a steady-state health target.

## Local Proof Runtimes

The repo also has three local proof runtimes that exercise the Go data plane
directly.

They are not yet separate deployed Kubernetes workloads in the public chart,
but they do follow the same shared admin contract:

- `collector-git`: `go run ./cmd/collector-git`
- `projector`: `go run ./cmd/projector`
- `reducer`: `go run ./cmd/reducer`

`collector-git` owns cycle orchestration, source-mode repository selection,
repo sync, durable fact commit, per-repo snapshot collection, content shaping,
the optional SCIP collector path, and the shared admin surface in Go.

The remaining hardening work on this branch is parity and validation, not
runtime ownership. The merge target remains full Go service ownership with no
normal-path Python delegation.

## Admin Contract

The platform rule is a consistent operator/admin contract across long-running
services:

- one shared status/report seam
- one CLI surface for local and on-host inspection
- one reusable HTTP/admin adapter that can be mounted by a runtime without
  redefining the report shape
- one API/admin surface when the transport is mounted
- explicit live-versus-inferred labeling
- stage, backlog, success, and failure summaries in a familiar shape

This is intentionally a platform rule, not a one-off `admin-status` feature.
Operators should not need a different mental model for collector, projector,
reducer, or future background services.

Current runtime status:

- `go/internal/status/` owns the shared reader/report seam
- `go/cmd/admin-status/` renders that report through the local CLI
- `go/internal/status/http.go` provides the reusable HTTP transport adapter
- `go/internal/runtime/admin.go` provides the shared runtime probe and admin
  route mount for `/healthz`, `/readyz`, optional `/metrics`, and optional
  `/admin/status`
- hosted Go runtimes can now compose that shared admin server into their
  lifecycle without bespoke HTTP bootstrap code
- the MCP runtime now composes that shared admin surface alongside its
  transport-specific routes
- the API runtime mounts that shared contract today
- `collector-git`, `projector`, and `reducer` all mount that shared admin
  surface in their local proof lanes
- the collector proof lane now uses native Go selection, repo sync, snapshot
  collection, content shaping, and optional SCIP execution/parsing
- the collector now emits Go-owned parser follow-up facts for workload identity
  and canonical code-call materialization, and the reducer owns the resulting
  `CALLS` edge reconciliation path
- the deleted Python bridge shims are no longer part of the branch
- parser, admin, and runtime ownership are Go-owned; remaining work is parity
  hardening and validation rather than preserving a dual-runtime architecture

## Incremental Refresh And Reconciliation

PCG should refresh incrementally by default and reconcile instead of forcing a
full re-index whenever possible.

- the `ingester` should reconcile only the scopes and generations that changed
- the `resolution-engine` should drain queued follow-up work and shared
  corrections from durable state
- `bootstrap-index` remains the one-shot escape hatch for empty environments or
  operator recovery
- future collector services should follow the same scope/generation contract
  rather than inventing a second freshness model

This means operators should use status, queue age, and generation state before
choosing to restart or reindex. A full re-index is a recovery tool, not the
normal freshness path.

## Naming Note

The public runtime names remain `platform-context-graph`, `mcp-server`,
`ingester`, and `resolution-engine`. Operators should still scale, monitor, and
troubleshoot those service identities, but the deployed processes are now Go
programs rather than Python CLI shims.

## Deployed Flow

```mermaid
flowchart LR
  A["Ingester"] --> B["Parse repository snapshot"]
  B --> C["Postgres fact store"]
  C --> D["Fact work queue"]
  D --> E["Resolution Engine"]
  E --> F["Neo4j"]
  E --> G["Postgres content store"]
  H["API"] --> F
  H --> G
  I["MCP Server"] --> F
  I --> G
```

## Local Full-Stack Flow

```mermaid
flowchart LR
  A["pcg-bootstrap-index"] --> B["Initial one-shot indexing"]
  C["ingester"] --> D["Ongoing sync and fact emission"]
  D --> E["Fact work queue"]
  E --> F["pcg-reducer"]
  G["platform-context-graph API"] --> H["Graph + content reads"]
```

## API

### Responsibilities

- serve HTTP query and admin requests
- read canonical graph state from Neo4j
- read file and entity content from Postgres
- serve operator/admin endpoints

### Does not own

- repository sync
- parsing
- fact emission
- queued projection work

### Deployments

- Compose service: `platform-context-graph`
- Helm template: `deploy/helm/platform-context-graph/templates/deployment.yaml`
- IaC chart template: `chart/templates/deployment.yaml`

### Signals to watch

- request latency and error rate
- content read latency
- graph query latency

Scale the API when request traffic rises. Do not scale it to fix queue backlog.

## MCP Server

### Responsibilities

- serve MCP SSE and JSON-RPC transport
- dispatch MCP tool calls over the mounted Go query surface
- expose the shared runtime admin surface plus MCP-specific health and session
  endpoints

### Does not own

- repository sync
- parsing
- fact emission
- queued projection work

### Deployments

- separate Go runtime started with `pcg mcp start`

### Signals to watch

- MCP session establishment and tool latency
- backend graph and content query latency
- transport health through `GET /health` plus shared readiness and status
  through `/healthz`, `/readyz`, `/admin/status`, and `/metrics`

Treat MCP as a separate query transport runtime, not as part of the API
process.

## Ingester

### Responsibilities

- discover and sync repositories
- own the shared workspace in Kubernetes
- parse repository snapshots
- emit facts into Postgres
- hand off durable projection work to the Go-owned write plane

### Why it stays stateful

The ingester is the only long-running runtime that should mount the workspace
PVC in Kubernetes.

### Deployments

- Compose service: `ingester`
- Helm template: `deploy/helm/platform-context-graph/templates/statefulset.yaml`
- IaC chart template: `chart/templates/statefulset.yaml`

### Signals to watch

- repository queue wait
- parse duration
- fact emission duration
- fact-store SQL latency
- workspace disk pressure

Scale or tune the ingester when parsing is the bottleneck or workspace pressure
is rising.

### Concurrency tuning

The ingester collector uses a goroutine worker pool for concurrent repository
snapshots. Set `PCG_SNAPSHOT_WORKERS` to control parallelism (default:
`min(NumCPU, 4)`). In Kubernetes, align CPU requests with the worker count to
avoid CPU throttling under concurrent parsing load.

## Resolution Engine

### Responsibilities

- claim fact work items
- load facts from Postgres
- project repository, file, entity, relationship, workload, and platform state
- persist projection decisions and bounded evidence
- manage retry, replay, dead-letter, and recovery workflows

### Deployments

- Compose service: `resolution-engine`
- Helm template:
  `deploy/helm/platform-context-graph/templates/deployment-resolution-engine.yaml`
- IaC chart template: `chart/templates/deployment-resolution-engine.yaml`

### Signals to watch

- queue depth and queue age
- claim latency
- per-stage projection duration
- per-stage output counts
- retry and dead-letter pressure
- Postgres queue and fact-store saturation

Scale the resolution-engine when queue age rises and workers remain busy. If
queue age rises together with Postgres contention, fix database pressure before
adding more workers.

### Concurrency tuning

The reducer supports concurrent intent execution (`PCG_REDUCER_WORKERS`,
default 1) and concurrent shared projection partition processing
(`PCG_SHARED_PROJECTION_WORKERS`, default 1). Increase these when queue age
rises and single-worker CPU is not saturated.

Additional shared projection config:

- `PCG_SHARED_PROJECTION_PARTITION_COUNT` (default 8) — partitions per domain
- `PCG_SHARED_PROJECTION_BATCH_LIMIT` (default 100) — intents per batch
- `PCG_SHARED_PROJECTION_POLL_INTERVAL` (default 5s) — cycle poll interval
- `PCG_SHARED_PROJECTION_LEASE_TTL` (default 60s) — partition lease TTL

In Kubernetes, size the Postgres connection pool to accommodate the total
concurrent workers across all reducer replicas. Each worker holds one
connection during claim/execute/ack.

## DB Migrate (Schema Init Container)

`pcg-bootstrap-data-plane` applies all Postgres and Neo4j schema DDL then
exits. It uses `CREATE TABLE IF NOT EXISTS` and `CREATE CONSTRAINT IF NOT
EXISTS` so it is safe to run repeatedly (idempotent).

### What it does

1. Connects to Postgres and runs `ApplyBootstrap` — creates all tables and
   indexes for facts, scopes, generations, content store, work queue, audit,
   relationships, shared intents, and projection decisions.
2. Connects to Neo4j and runs `EnsureSchema` — creates all node constraints,
   uniqueness indexes, performance indexes, and full-text indexes.
3. Exits with code 0 on success.

### Why it exists

Without this service, downstream runtimes (API, MCP, ingester, reducer)
had to wait for `bootstrap-index` to finish its full data population run
(50+ minutes on 895 repos) before starting. The schema init container
decouples DDL from data: services come up within seconds and serve traffic
on an empty-but-valid schema while bootstrap-index populates data in the
background.

### Docker Compose

In Compose, `db-migrate` is a short-lived service that exits after applying
schemas. All other services depend on it with
`condition: service_completed_successfully`:

```yaml
db-migrate:
  image: platform-context-graph:dev
  command: ["/usr/local/bin/pcg-bootstrap-data-plane"]
  environment:
    DEFAULT_DATABASE: neo4j
    NEO4J_URI: bolt://neo4j:7687
    NEO4J_USERNAME: neo4j
    NEO4J_PASSWORD: change-me
    PCG_POSTGRES_DSN: postgresql://pcg:change-me@postgres:5432/platform_context_graph
  depends_on:
    neo4j:
      condition: service_healthy
    postgres:
      condition: service_healthy
```

### EKS / Kubernetes Init Container

In EKS, add `pcg-bootstrap-data-plane` as an `initContainer` on every
Deployment and StatefulSet that needs database access. The init container
runs before the main container starts, ensuring schemas exist.

```yaml
# Example: API Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: platform-context-graph
spec:
  template:
    spec:
      initContainers:
        - name: db-migrate
          image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
          command: ["/usr/local/bin/pcg-bootstrap-data-plane"]
          env:
            - name: PCG_POSTGRES_DSN
              valueFrom:
                secretKeyRef:
                  name: pcg-db-credentials
                  key: dsn
            - name: NEO4J_URI
              value: bolt://neo4j:7687
            - name: NEO4J_USERNAME
              valueFrom:
                secretKeyRef:
                  name: pcg-neo4j-credentials
                  key: username
            - name: NEO4J_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: pcg-neo4j-credentials
                  key: password
            - name: DEFAULT_DATABASE
              value: neo4j
      containers:
        - name: api
          image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
          command: ["/usr/local/bin/pcg-api"]
          # ...
```

Apply the same init container to:

| Workload | Kind | Why |
| --- | --- | --- |
| `platform-context-graph` (API) | `Deployment` | Reads from Postgres + Neo4j |
| `mcp-server` | `Deployment` | Reads from Postgres + Neo4j |
| `ingester` | `StatefulSet` | Writes facts to Postgres |
| `resolution-engine` (reducer) | `Deployment` | Writes to Postgres + Neo4j |

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `PCG_POSTGRES_DSN` | Yes | Postgres connection string |
| `NEO4J_URI` | Yes | Neo4j Bolt URI |
| `NEO4J_USERNAME` | Yes | Neo4j auth username |
| `NEO4J_PASSWORD` | Yes | Neo4j auth password |
| `DEFAULT_DATABASE` | No | Neo4j database name (default: `neo4j`) |

### Operational notes

- **Idempotent**: safe to run on every pod start — all DDL uses `IF NOT EXISTS`.
- **Fast**: completes in under 5 seconds on a warm database.
- **No data dependency**: does not populate any data, only creates empty tables
  and indexes. Data is populated by `bootstrap-index` or `ingester`.
- **Failure handling**: if the init container fails (database unreachable),
  Kubernetes will retry the pod according to `restartPolicy`. The main
  container will not start until schema migration succeeds.
- **Rolling updates**: when deploying a new version with schema changes, the
  init container on the first pod to roll applies the new DDL. Subsequent pods
  see it already applied (idempotent).

## Bootstrap Index

Bootstrap indexing is a one-shot operator activity, not a long-running
Kubernetes workload in the public Helm chart.

Use it when you want to:

- materialize an initial repository set quickly
- reduce cold-start time on a brand-new environment
- validate end-to-end indexing against a known repository set

Today it is packaged directly in Docker Compose and can also be run manually as
a direct process. Treat repeated restarts or long-running bootstrap activity as
an incident.

## Metrics And ServiceMonitor

### Local Compose

Compose exposes direct runtime scrape endpoints you can curl:

- API: `http://localhost:19464/metrics`
- Ingester: `http://localhost:19465/metrics`
- Resolution Engine: `http://localhost:19466/metrics`

### Kubernetes

Helm can expose the same runtime metrics over dedicated ports and can also
render `ServiceMonitor` resources for:

- API
- Ingester
- Resolution Engine

`ServiceMonitor` does not apply to the bootstrap helper because it is not a
steady-state Kubernetes service in the public chart.

## Operator Defaults

- treat API, ingester, and resolution-engine as separate scaling units
- keep the workspace mounted only on the ingester in Kubernetes
- use direct `/metrics` endpoints for local verification
- use `ServiceMonitor` only for the long-running Kubernetes runtimes
- treat the local proof runtimes as milestone-validation tools unless and until
  the public deployment contract promotes them into steady-state deployed
  shapes
- treat the shared admin/status report as the first place to look for live,
  inferred, backlog, and failure state
- prefer incremental scope refresh and reconciliation over platform-wide
  re-indexing
- use the [Telemetry Overview](../reference/telemetry/index.md) to decide which
  signal to inspect first
- use the [Local Testing Runbook](../reference/local-testing.md) before calling
  a change ready
