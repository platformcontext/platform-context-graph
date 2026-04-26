# Local Testing Runbook

This is the default verification runbook for engineers, Claude, and Codex on
the current platform.

Use it to answer:

- which commands should I run for this kind of change
- what is the minimum acceptable verification before I call work ready
- how do I run the local full-stack workflow
- how do I validate metrics, traces, and the facts-first pipeline

## Start Here

Treat this file as the verification source of truth.

Before changing runtime or deployment behavior, also read:

- [Service Runtimes](../deployment/service-runtimes.md)
- [Docker Compose](../deployment/docker-compose.md)
- [Telemetry Overview](./telemetry/index.md)

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
```

## Local API Auth

Local compose keeps auth at the Go API boundary.

- If `PCG_API_KEY` is explicitly set for the running `platform-context-graph`
  container, the compose verification scripts use it as the bearer token.
- If no explicit env token is present, the Go runtime can reuse a persisted
  token from `PCG_HOME/.env` or generate one when
  `PCG_AUTO_GENERATE_API_KEY=true`, and the verification scripts check that
  same file.
- If neither source contains a token, the local stack runs without bearer auth
  and the verification scripts omit the header.
- There is no separate auth service, login flow, or OAuth dependency in this
  local contract.

## Compose Host-Path Rules

When you run the stack against host repositories, the bind root must be an
absolute path to a real directory.

- Do not use a symlinked path.
- Do not rely on `~` expansion inside Compose files.
- On macOS, do not use `/tmp` as the host root because Docker Desktop resolves
  it through `/private/tmp`.
- If you copied repositories for Compose testing, copy them into a real
  directory under your home folder and point `PCG_FILESYSTEM_HOST_ROOT` there.

## Quick Verification Matrix

| If you touched | Minimum verification |
| --- | --- |
| Docs, `CLAUDE.md`, `AGENTS.md`, or README files | `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml` |
| CLI/runtime wiring | `cd go && go test ./cmd/pcg ./cmd/api ./cmd/mcp-server -count=1` |
| Status/admin or completeness contract | `cd go && go test ./internal/status ./internal/query ./cmd/api -count=1` and `cd go && go vet ./internal/status ./internal/query ./cmd/api` |
| Parser platform or collector snapshot flow | `cd go && go test ./internal/parser ./internal/collector/discovery ./internal/collector -count=1` |
| Terraform provider-schema evidence or relationship extraction | `cd go && go test ./internal/terraformschema ./internal/relationships ./internal/storage/postgres -count=1` |
| Compose, Helm, or deployable runtime shape | `cd go && go test ./cmd/api ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer -count=1` and `helm lint deploy/helm/platform-context-graph` |
| Correlation DSL fixture corpus or compose verification lane | `./scripts/verify_correlation_dsl_compose.sh` |
| Graph-backed call-chain, caller/callee, or dead-code compose contract | `./scripts/verify_graph_analysis_compose.sh` |
| Facts-first indexing, queue, or resolution flow | `cd go && go test ./internal/projector ./internal/reducer ./internal/storage/postgres -count=1` |
| Local-authoritative graph backend or MCP local coding flow | `cd go && go test ./cmd/ingester ./internal/projector ./internal/storage/neo4j -count=1`; then run the manual NornicDB MCP smoke below if a local NornicDB binary is available |
| Queue ack visibility or lease diagnosis | `cd go && go test ./internal/projector ./internal/reducer ./internal/status ./internal/storage/postgres ./internal/telemetry -count=1` and `cd go && go vet ./internal/projector ./internal/reducer ./internal/status ./internal/storage/postgres ./internal/telemetry` |
| Recovery, replay, or repair controls | `cd go && go test ./internal/recovery ./internal/runtime ./internal/status -count=1` |
| Facts-first telemetry or queue scaling | `cd go && go test ./internal/telemetry ./internal/runtime ./internal/projector ./internal/reducer -count=1` |
| Admin replay flow | `cd go && go test ./internal/query ./internal/recovery ./internal/runtime -count=1` |
| Repo hygiene gates | `git diff --check` |

## Go Runtime Package Gate

Use this gate when validating the current runtime and collector wiring.

Current ownership:

- `collector-git` owns cycle orchestration, discovery, snapshotting, parsing,
  content shaping, and durable fact commit
- `projector` owns source-local materialization stages and decision recording
- `reducer` owns queued shared projection, platform materialization,
  dependency projection, repair flows, and recovery ownership
- `status` owns scan/reindex request lifecycle
- only long-running hosted runtimes that mount `go/internal/runtime` expose
  `/healthz`, `/readyz`, `/metrics`, and `/admin/status`
- one-shot helpers such as `bootstrap-index` emit telemetry through OTEL
  exporters but do not mount the shared HTTP admin surface

Focused Go package gate:

```bash
cd go
go test ./internal/parser ./internal/collector/discovery ./internal/content/shape \
  ./internal/collector ./cmd/collector-git ./cmd/ingester ./cmd/bootstrap-index \
  ./internal/runtime ./internal/app ./internal/telemetry \
  ./internal/storage/neo4j ./internal/storage/postgres \
  ./internal/projector ./internal/reducer ./cmd/reducer -count=1
```

## Local-Authoritative MCP Smoke

Use this smoke when touching the NornicDB sidecar, graph-backend selection,
projector stage ordering, or local MCP code-search behavior. It requires a
local NornicDB binary such as `/tmp/nornicdb-headless`.
For the consolidated list of NornicDB environment variables and when to use
each one, see [NornicDB Tuning](nornicdb-tuning.md).

Until `https://github.com/orneryd/NornicDB/pull/119` is merged and published
as a pinned release asset, use a headless binary built from the
`pcg-sql-edge-hotpath` PR branch for repo-scale `local_authoritative` dogfood
and graph-query validation. That branch contains the SQL relationship hot path
and node-lookup cache fixes that the current PCG dogfood evidence depends on.
On the remote 16-vCPU dogfood host, the current validated binary path is:

```bash
export PCG_NORNICDB_BINARY=/home/ubuntu/os-repos/NornicDB/bin/nornicdb-headless-pcg-sql-edge-hotpath
```

Before every local-authoritative dogfood run, rebuild the owner and child
binaries and put `go/bin` on `PATH`; otherwise `pcg graph start` can launch a
fresh owner from current source but fail when it tries to discover
`pcg-reducer` or `pcg-ingester`.

```bash
cd go
go build -o ./bin/pcg ./cmd/pcg
go build -o ./bin/pcg-api ./cmd/api
go build -o ./bin/pcg-ingester ./cmd/ingester
go build -o ./bin/pcg-reducer ./cmd/reducer
export PATH="$PWD/bin:$PATH"
```

On a local workstation, rebuild from the PR branch with the no-local-LLM tags
before setting `PCG_NORNICDB_BINARY`:

```bash
cd /Users/allen/os-repos/NornicDB-pcg-sql-edge-hotpath
go build -tags 'noui nolocalllm' -o ./bin/nornicdb-headless-pcg-sql-edge-hotpath ./cmd/nornicdb
export PCG_NORNICDB_BINARY=/Users/allen/os-repos/NornicDB-pcg-sql-edge-hotpath/bin/nornicdb-headless-pcg-sql-edge-hotpath
```

```bash
export PCG_HOME=/tmp/pcg-local-authoritative-smoke
export PCG_CANONICAL_WRITE_TIMEOUT=2s
export PCG_NORNICDB_PHASE_GROUP_STATEMENTS=500
export PCG_NORNICDB_FILE_PHASE_GROUP_STATEMENTS=5
export PCG_NORNICDB_FILE_BATCH_SIZE=100
export PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS=25
export PCG_NORNICDB_ENTITY_BATCH_SIZE=100
export PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES=Function=15,Struct=50,Variable=10,K8sResource=1
export PCG_NORNICDB_ENTITY_LABEL_PHASE_GROUP_STATEMENTS=Function=5,Struct=15,Variable=5,K8sResource=1
export PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES=Annotation=10,Function=10,Variable=10,Module=10,ImplBlock=10
./go/bin/pcg install nornicdb --from /tmp/nornicdb-headless
./go/bin/pcg graph start --workspace-root "$PWD"
./go/bin/pcg mcp start --workspace-root "$PWD"
```

`pcg graph start` applies both local Postgres schema and the NornicDB graph
schema before it publishes the owner record or starts reducer/ingester
children. This ordering is required for NornicDB's schema-backed `MERGE` hot
paths; if the graph schema bootstrap fails, do not continue into projection.

`pcg graph start` now renders a live terminal progress panel while the local
host indexes and projects: owner/profile/backend header, collector/projector/
reducer flow lanes, and queue pressure from the shared status store. Treat
that panel as truthful runtime status, not as a percentage-complete contract.
For first-generation scopes, canonical graph projection skips stale-generation
retraction because no prior generation exists yet; refresh runs and follow-up
generations after a failed first attempt still perform scoped retraction before
upserting the new generation.

From an MCP client, call:

- `search_file_content` with a symbol or unique string from the repo
- `find_code` with the same symbol
- `get_index_status`

The smoke passes when content-index-backed tools return real repo results with
`truth.profile=local_authoritative` and `truth.basis=content_index`, even if
`get_index_status` reports degraded graph projection while NornicDB remains
under evaluation. Always finish with `pcg graph stop --workspace-root "$PWD"`
and verify `pcg graph status` reports `owner_present=false`.

Do not set `PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` for this everyday MCP
smoke. That switch is reserved for adapter conformance runs that intentionally
exercise NornicDB's Bolt explicit transaction path and verify rollback,
timeout, and no-partial-write behavior. If repo-scale projection is the thing
you are validating, tune `PCG_NORNICDB_PHASE_GROUP_STATEMENTS` before you reach
for grouped conformance mode so the everyday local-authoritative path stays the
thing under test. Use `PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS` when the
repo-scale hotspot is specifically the canonical `entities` phase and you need
smaller entity-only grouped transactions without shrinking every other phase.
Use `PCG_NORNICDB_FILE_PHASE_GROUP_STATEMENTS` when the hotspot is the
canonical `files` phase on repos with thousands of files; this narrows only
file-upsert grouped transactions and leaves repository, directory, module, and
structural-edge phases on the broader phase-group default.
Use `PCG_NORNICDB_FILE_BATCH_SIZE` when a file-phase group is already narrow
but one `File` upsert statement still carries too many rows. This controls the
row count inside each `phase=files` statement, while
`PCG_NORNICDB_FILE_PHASE_GROUP_STATEMENTS` controls how many such statements
share one grouped Bolt transaction.
Use `PCG_NORNICDB_ENTITY_BATCH_SIZE` when the problem is the number of rows
inside each normal batched entity upsert statement rather than the number of
statements in a grouped transaction.
The current NornicDB writer also keeps `Function` entity upserts on a narrower
internal row batch than the broader entity default because repo-scale dogfood
showed `Function` rows remain the heaviest entity shape on this repository.
Use `PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES=Function=15,Struct=50,Variable=10,K8sResource=1`
when you need to tune specific heavy entity families without recompiling or
lowering the row cap for the entire entity phase. `K8sResource` needs both a
row cap and a grouped-statement cap: Helm/Kustomize manifests can contain many
resources in one file, and full-corpus timing showed even five same-file rows
can exceed the bounded write budget under concurrent K8s-heavy projection.
If those row caps are already narrow but the grouped entity chunks are still
too large, use
`PCG_NORNICDB_ENTITY_LABEL_PHASE_GROUP_STATEMENTS=Function=5,Struct=15,Variable=5,K8sResource=1`
to shrink only the grouped transaction size for those heavier families without
forcing the same statement cap onto every other entity label.
Reducer-owned semantic entity materialization has its own high-cardinality
label caps because it runs after source-local canonical projection and writes
parser-enriched semantic labels such as `Function` and `Variable`. Use
`PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES=Function=15,Variable=10` when
that reducer domain times out; NornicDB semantic writes use the same row-map
merge shape as the canonical hot path, and timeout errors include the semantic
label and row count that tripped the deadline.
Semantic retract is a separate reducer-owned cleanup step. First-generation
semantic materialization skips it entirely because there is no prior semantic
graph state to clean up. Refreshes and retries still retract; Neo4j keeps the
single broad multi-label retract, while NornicDB uses one label-scoped retract
per semantic label because repo-scale timing showed the broad shape can scan
and timeout even when the write rows are otherwise bounded.
When you are tuning repo-scale entity projection, do not decide from one scary
chunk log alone. NornicDB currently uses a file-scoped combined entity write
because its current binary does not correctly preserve row-bound identity in
the standalone node-only batch shape. Backends that support that node-only
shape can still split entity node upsert from `phase=entity_containment`. If
you are testing a patched NornicDB binary with row-safe `SET += row.props`
support in the generalized `UNWIND/MERGE` hot path and unique-constraint-backed
`MERGE` lookup, set `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true` to try the
faster MERGE-first combined shape that batches entity rows across files. Leave
that switch off for the pinned release-backed binary.
Use the emitted `nornicdb entity label summary` lines to compare cumulative
rows, statements, executions, grouped chunks, and total/max duration per
`phase` and label before changing another default. Long-running labels emit
rolling summaries every 10 executions and a final summary at label completion,
so you do not need to wait for an hour-scale phase to finish before you can
see whether the cumulative cost is node row width, containment edges, grouped
transaction size, or label ordering.
If a run is still progressing linearly after schema-backed `MERGE` lookup is
confirmed, stop treating batch size as the only control knob. Use a
pprof-enabled NornicDB binary with `NORNICDB_ENABLE_PPROF=true` and capture CPU
and heap profiles during the hot label before changing another default.

### Local-Authoritative Startup Envelope Smoke

Use this gate when touching local-host startup ordering, embedded Postgres
boot, NornicDB sidecar boot, or owner-record readiness for
`local_authoritative`.

```bash
PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless \
PCG_LOCAL_AUTHORITATIVE_PERF=true \
  go test ./cmd/pcg -run TestLocalAuthoritativeStartupEnvelope -count=1 -v
```

The smoke passes when:

- the first startup reaches the owner-record plus ingester handoff in under
  15 seconds
- the second startup against the same workspace data root reaches the same
  readiness point in under 5 seconds
- the owner record proves `profile=local_authoritative` and
  `graph_backend=nornicdb` before the ingester is launched

Recorded sample on 2026-04-23 against the pinned bare-install binary at
`/tmp/pcg-bare-install-smoke/bin/nornicdb-headless`:

- cold start: `9.045253708s`
- warm restart: `490.996625ms`

### Local-Authoritative Call-Chain Query Perf Smoke

Use this gate when touching graph-backed call-chain analysis, NornicDB query
compatibility routing, or the `local_authoritative` call-chain handler path.

```bash
PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless \
PCG_LOCAL_AUTHORITATIVE_PERF=true \
  go test ./cmd/pcg -run TestLocalAuthoritativeCallChainSyntheticEnvelope -count=1 -v
```

The smoke passes when:

- the real `local_authoritative` host boots successfully
- the synthetic four-function `CALLS` chain is written through the shared Bolt
  driver path
- `/api/v0/code/call-chain` returns non-empty path nodes with
  `truth.profile=local_authoritative` and
  `truth.basis=authoritative_graph`
- the synthetic call-chain p95 remains under 2 seconds

Recorded sample on 2026-04-23 against the pinned bare-install binary at
`/tmp/pcg-bare-install-smoke/bin/nornicdb-headless`:

- synthetic call-chain p95: `736.25µs`

This gate is intentionally narrower than the full active-repo performance
envelope. It proves the backend-routed NornicDB call-chain query shape and
live handler path before broader repo-scale perf work continues.

### Local-Authoritative Transitive-Caller Query Perf Smoke

Use this gate when touching graph-backed transitive callers/callees,
NornicDB traversal compatibility routing, or the `local_authoritative`
`/api/v0/code/relationships` handler path.

```bash
PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless \
PCG_LOCAL_AUTHORITATIVE_PERF=true \
  go test ./cmd/pcg -run TestLocalAuthoritativeTransitiveCallersSyntheticEnvelope -count=1 -v
```

The smoke passes when:

- the real `local_authoritative` host boots successfully
- the synthetic four-function `CALLS` chain is written through the shared Bolt
  driver path
- `/api/v0/code/relationships` returns three indirect callers for the seeded
  terminal function with `truth.capability=call_graph.transitive_callers`
- the farthest synthetic caller is reported at depth `3`
- the synthetic transitive-caller p95 remains under 2 seconds

Recorded sample on 2026-04-23 against the pinned bare-install binary at
`/tmp/pcg-bare-install-smoke/bin/nornicdb-headless`:

- synthetic transitive-caller p95: `1.917916ms`

### Local-Authoritative Dead-Code Query Perf Smoke

Use this gate when touching graph-backed dead-code analysis, NornicDB
candidate-query compatibility routing, or the `local_authoritative`
`/api/v0/code/dead-code` handler path.

```bash
PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless \
PCG_LOCAL_AUTHORITATIVE_PERF=true \
  go test ./cmd/pcg -run TestLocalAuthoritativeDeadCodeSyntheticEnvelope -count=1 -v
```

The smoke passes when:

- the real `local_authoritative` host boots successfully
- a synthetic repository/file/function containment graph is written through the
  shared Bolt driver path
- `/api/v0/code/dead-code` returns the two intentionally uncalled functions
  with `truth.capability=code_quality.dead_code`
- the synthetic dead-code p95 remains under 10 seconds

Recorded sample on 2026-04-23 against the pinned bare-install binary at
`/tmp/pcg-bare-install-smoke/bin/nornicdb-headless`:

- synthetic dead-code p95: `3.174125ms`

This gate is intentionally narrower than the full active-repo performance
envelope. It proves the backend-routed NornicDB dead-code candidate query and
derived-policy filter path before broader repo-scale perf work continues.

## Compose Graph-Analysis Verification

Use this gate when touching authoritative graph-backed code analysis that must
work end to end through the full Compose stack.

```bash
./scripts/verify_graph_analysis_compose.sh
```

The wrapper starts a clean Compose stack against the dedicated
`tests/fixtures/graph_analysis_compose` corpus and proves:

- direct callers resolve from canonical `CALLS` edges
- transitive callers return the expected depth-aware chain
- call-chain path search returns the expected shortest path
- dead-code analysis returns only the intentionally unused functions with
  derived truth metadata
- the canonical Neo4j graph contains the expected `CALLS` edges after the
  fresh bootstrap run

### NornicDB Grouped-Write Safety Probe

Use this opt-in gate when touching NornicDB grouped canonical writes or the
`PCG_NORNICDB_CANONICAL_GROUPED_WRITES` conformance switch:

```bash
PCG_NORNICDB_BINARY=/tmp/nornicdb-headless \
  go test ./cmd/pcg -run TestNornicDBGroupedWriteSafetyProbe -count=1 -v
```

As of the 2026-04-23 evaluation, the probe proves these facts against the
rebuilt linuxdynasty-fork headless binary
`/tmp/nornicdb-headless-pcg-rollback` (`v1.0.42-hotfix`):

- PCG canonical grouped writes can commit the basic repository/file/function
  node shape.
- Client-side grouped write timeout prevents the timeout probe from partially
  committing.
- Grouped rollback, clean explicit rollback, and failed-statement explicit
  rollback all report marker count `0` on the PCG Neo4j-driver path.

The promotion gate is intentionally stricter than the observable safety probe:

```bash
PCG_NORNICDB_BINARY=/tmp/nornicdb-headless-pcg-rollback \
PCG_NORNICDB_REQUIRE_GROUPED_ROLLBACK=true \
  go test ./cmd/pcg -run TestNornicDBGroupedWriteRollbackConformance -count=1 -v
```

Normal laptop runs still leave `PCG_NORNICDB_CANONICAL_GROUPED_WRITES` unset
until a fixed NornicDB binary is release-backed and the broader adapter matrix
passes.

## Terraform Provider-Schema Gate

Use this gate when touching the Terraform provider-schema runtime path or the
schema-driven relationship extractors.

```bash
cd go
go test ./internal/terraformschema ./internal/relationships ./internal/storage/postgres -count=1
```

The canonical packaged schemas live under:

- `go/internal/terraformschema/schemas/*.json.gz`

If this gate fails, fix the Go loader or the Go relationship extraction path.

The relationship-platform compose verification now validates the full
cross-repo path, including:

- repository selection from the fixture corpus via `PCG_REPOSITORY_RULES_JSON`
- reducer normalization of repository IDs before edge writes
- persistence of typed `evidence_type` metadata on repo edges so repository
  contexts surface `controller_driven`, `workflow_driven`, and `iac_driven`
  relationship families

The correlation DSL compose verification exercises the generic multi-repo
fixture corpus, exact filesystem repository selection, and the current
admitted-versus-provenance-only proof scaffolding:

```bash
./scripts/verify_correlation_dsl_compose.sh
```

The verifier now checks the fixture tree before Compose starts and then
confirms repository-context coverage for these open-source-safe delivery
families:

- GitHub Actions plus Dockerfile (`service-gha`)
- Jenkins plus Dockerfile (`service-jenkins`)
- Jenkins plus Ansible handoff (`service-jenkins-ansible`)
- Docker Compose runtime artifacts (`service-compose`)
- Terraform stack repositories (`terraform-stack-gha`, `terraform-stack-jenkins`)
- Mixed Dockerfile admission and rejection cases (`multi-dockerfile-repo`)

On failure, the script prints the last verification step, `docker compose ps`,
the expected repository set derived from the fixture root, the latest API
payload captures, a resolution-engine metrics sample, and the Jaeger URL.

## Runtime Tree Hygiene

The deployable runtime tree is Go-only. Use this check when you need to confirm
that no runtime implementation has drifted outside the documented Go packages.

```bash
rg --files . -g '*.py' | rg -v '^(\\./)?tests/fixtures/'
```

That command should return no runtime Python files. Fixture data under
`tests/fixtures/` and explicitly offline-only tooling can still carry Python
source when they are not part of the deployable runtime.

## Bootstrap Projection Concurrency

The `bootstrap-index` one-shot runtime runs projection concurrently using a
goroutine worker pool. Each worker claims a scope-generation work item from
the Postgres projector queue (`SELECT ... FOR UPDATE SKIP LOCKED`) and
independently loads facts, projects, and acks.

### Tuning

| Env var | Default | Description |
| --- | --- | --- |
| `PCG_PROJECTION_WORKERS` | `min(NumCPU, 8)` | Number of concurrent projection goroutines |

Set `PCG_PROJECTION_WORKERS=1` to force sequential processing (useful for
debugging). Values above 8 are supported for machines with high core counts
and fast I/O to Postgres and Neo4j.

### Telemetry signals for tuning

Go data-plane signals use the `pcg_dp_` prefix, and service-health/runtime
gauges use the `pcg_runtime_` prefix on the same `/metrics` surface.

| Signal | Type | What it tells you |
| --- | --- | --- |
| `pcg_dp_projector_run_duration_seconds` | histogram | Per-item projection wall time. High P95 on a single scope means a large repo is the bottleneck. |
| `pcg_dp_queue_claim_duration_seconds{queue=projector}` | histogram | Time to claim work from Postgres. High values mean lock contention — reduce workers or tune Postgres. |
| `pcg_dp_projections_completed_total{status}` | counter | Success/failure rate. Track `status=failed` for projection errors. |
| `pcg_dp_facts_emitted_total` | counter | Total facts produced by the collector phase. |
| `pcg_dp_facts_committed_total` | counter | Total facts durably committed before projection starts. |
| `pcg_dp_collector_observe_duration_seconds` | histogram | Per-scope collection wall time. Dominated by Git discovery and parsing. |

Structured JSON logs include `worker_id`, `scope_id`, `fact_count`,
`duration_seconds`, and `pipeline_phase` on every projection line:

```json
{"message":"bootstrap projection succeeded","scope_id":"my-repo","worker_id":3,"fact_count":1234,"duration_seconds":2.5,"pipeline_phase":"projection"}
```

Filter by `pipeline_phase=projection` and group by `worker_id` to identify
worker imbalance (one worker stuck on a large repo while others idle).

### Concurrency model

```text
main goroutine
  |
  |-- drainCollector (sequential: sync -> discover -> parse -> commit)
  |
  |-- drainProjector (N goroutine workers)
        |-- worker 0: Claim -> LoadFacts -> Project -> Ack (loop)
        |-- worker 1: Claim -> LoadFacts -> Project -> Ack (loop)
        |-- ...
        |-- worker N-1: Claim -> LoadFacts -> Project -> Ack (loop)
        |
        On first error: cancel shared context -> all workers drain -> errors.Join
```

## Concurrency Tuning Reference

All Go data plane services support environment-driven concurrency tuning.
Set any variable to `1` to force sequential processing (useful for debugging).

| Env Var | Default | Service | What It Controls |
| --- | --- | --- | --- |
| `PCG_PROJECTION_WORKERS` | `min(NumCPU, 8)` | Bootstrap-Index | Concurrent bootstrap projection goroutines |
| `PCG_SNAPSHOT_WORKERS` | `min(NumCPU, 4)` | Ingester / Bootstrap | Concurrent repository snapshot goroutines |
| `PCG_REDUCER_WORKERS` | 1 (sequential) | Reducer | Concurrent reducer intent execution goroutines |
| `PCG_SHARED_PROJECTION_WORKERS` | 1 (sequential) | Reducer | Concurrent shared projection partition goroutines |
| `PCG_SHARED_PROJECTION_PARTITION_COUNT` | 8 | Reducer | Number of partitions per shared projection domain |
| `PCG_SHARED_PROJECTION_BATCH_LIMIT` | 100 | Reducer | Max intents processed per partition batch |
| `PCG_SHARED_PROJECTION_POLL_INTERVAL` | 5s | Reducer | Shared projection cycle poll interval |
| `PCG_SHARED_PROJECTION_LEASE_TTL` | 60s | Reducer | Partition lease time-to-live |

### Queue diagnosis expectations

For projector and reducer queue work, validate more than happy-path execution:

- expired claims can be reclaimed by the normal claim SQL
- overdue claims surface through status
- ack failures emit dedicated logs and metrics instead of hiding inside generic
  execution failures
- structured logs keep failure class, queue name, and work item identity

Use the telemetry guide together with the focused queue gate above when you
touch those paths.

### Collector Concurrency Model

```text
ingester / bootstrap-index
  |
  |-- GitSource.buildCollected (N snapshot workers)
        |-- worker 0: SnapshotRepository -> buildFacts -> collect (loop)
        |-- worker 1: SnapshotRepository -> buildFacts -> collect (loop)
        |-- ...
        |-- worker N-1: SnapshotRepository -> buildFacts -> collect (loop)
        |
        On first error: cancel shared context -> all workers drain
```

### Reducer Concurrency Model

```text
reducer service
  |
  |-- runMainLoop (N reducer workers)
  |     |-- worker 0: Claim -> Execute -> Ack/Fail (loop)
  |     |-- worker 1: Claim -> Execute -> Ack/Fail (loop)
  |     |-- ...
  |
  |-- SharedProjectionRunner (M partition workers)
        |-- worker 0: lease -> batch select -> edge write -> release (loop)
        |-- worker 1: lease -> batch select -> edge write -> release (loop)
        |-- ...
        |
        3 domains × K partitions = 3K work items per cycle
```

## Live Runtime Verification Scripts

These scripts allocate their own local ports, start only the required
compose-backed infrastructure, and tear the stack down automatically unless
`PCG_KEEP_COMPOSE_STACK=true` is set.

They are shell-native Go-runtime verification scripts.

Run them one at a time. They all reuse the same local Compose project name, so
parallel runs will fight over container and network ownership even if the host
ports differ.

```bash
./scripts/verify_collector_git_runtime_compose.sh
./scripts/verify_projector_runtime_compose.sh
./scripts/verify_reducer_runtime_compose.sh
./scripts/verify_incremental_refresh_compose.sh
./scripts/verify_relationship_platform_compose.sh
./scripts/verify_admin_refinalize_compose.sh
```

`verify_relationship_platform_compose.sh` exports exact repository rules for the
checked-in relationship fixture corpus before booting Compose. That corpus keeps
fixture metadata at its root, so explicit rules prevent the metadata file from
collapsing the whole corpus into a single synthetic repository during
verification runs.

## Local Full Stack

### With fixture ecosystems (default)

Start the full stack with the bundled test fixtures:

```bash
docker compose up --build
```

### With real repositories

To test against real Git repositories from a local directory, set
`PCG_FILESYSTEM_HOST_ROOT` to an absolute path containing one or more
cloned repositories. Each subdirectory with a `.git` folder is
discovered automatically. The collector prunes dependency and generated
artifact directories such as `.git`, `node_modules`, `vendor`, and `.yarn`
before parsing so checked-in package-manager bundles do not dominate the graph.

```bash
PCG_FILESYSTEM_HOST_ROOT=/path/to/your/repos docker compose up --build
```

Port overrides are available when default ports conflict with other
services (SSH tunnels, other Compose stacks, etc.):

```bash
PCG_FILESYSTEM_HOST_ROOT=/path/to/your/repos \
  PCG_POSTGRES_PORT=25432 \
  NEO4J_HTTP_PORT=27474 \
  NEO4J_BOLT_PORT=27687 \
  PCG_HTTP_PORT=28080 \
  PCG_MCP_PORT=28081 \
  JAEGER_UI_PORT=26686 \
  docker compose up --build
```

Local full-stack runs now also cap the Neo4j Docker heap and page cache by
default so single-repo dogfood runs do not depend on the container choosing an
unbounded JVM profile. Override them when you need a larger local graph store:

```bash
PCG_NEO4J_HEAP_INITIAL_SIZE=768m \
PCG_NEO4J_HEAP_MAX_SIZE=768m \
PCG_NEO4J_PAGECACHE_SIZE=768m \
docker compose up --build
```

**Important notes for real repo testing:**

- The path must be a real directory (not a symlink). On macOS, `/tmp`
  is a symlink to `/private/tmp` which Docker Desktop cannot resolve.
  Use a path under `/Users/` or `/home/`.
- Each repo subdirectory must contain a `.git` directory.
- Large repo sets (10+ repos, thousands of files) require significant
  memory. The bootstrap-index process holds all parsed facts in memory
  during the commit phase. For large repo sets, use a machine with at
  least 16 GB of RAM allocated to Docker.
- The Compose stack bounds Neo4j to `512m` heap and `512m` page cache by
  default through `PCG_NEO4J_HEAP_INITIAL_SIZE`,
  `PCG_NEO4J_HEAP_MAX_SIZE`, and `PCG_NEO4J_PAGECACHE_SIZE`. Increase them
  explicitly if a larger real-repo graph run needs more headroom.
- Symlinks inside repositories are skipped during the filesystem copy
  phase. This is intentional — symlinks cannot be reliably resolved
  inside the container.

### Services

Both modes bring up:

- Neo4j
- Postgres
- OTEL collector + Jaeger
- `bootstrap-index` (one-shot, seeds the graph and fact store)
- `platform-context-graph` (HTTP API)
- `mcp-server` (MCP tool server)
- `ingester` (ongoing repo sync)
- `resolution-engine` (reducer / shared projection)

### Useful checks

```bash
docker compose ps
docker compose logs bootstrap-index | tail -50
docker compose logs ingester | tail -50
docker compose logs resolution-engine | tail -50
```

### Sync the local MCP client config

When the Compose stack auto-picks ports or generates a fresh bearer token, resync
the checked-in `.mcp.json` before using Codex or another MCP client against the
local stack:

```bash
./scripts/sync_local_compose_mcp.sh
```

That helper:

- discovers the live published `mcp-server` and API ports from `docker-compose`
- reads the current bearer token from the running `mcp-server` container
- updates only the `pcg-local-compose` entry in `.mcp.json`
- preserves remote entries such as `pcg-e2e`
- probes MCP health, MCP `tools/list`, and API `index-status`

Use the same `COMPOSE_PROJECT_NAME` value here that you used for
`docker compose up` if you ran a named stack:

```bash
COMPOSE_PROJECT_NAME=pcg-one-repo ./scripts/sync_local_compose_mcp.sh
```

The default target file is the repo-local `.mcp.json`, which is the config we
use for Codex and Claude in this repository. If you need to update a different
client config file, override it:

```bash
PCG_MCP_CONFIG_FILE="$HOME/path/to/mcp.json" \
./scripts/sync_local_compose_mcp.sh
```

If you want a different server key than `pcg-local-compose`, override the entry
name too:

```bash
PCG_LOCAL_MCP_SERVER_NAME=pcg-local-one-repo \
./scripts/sync_local_compose_mcp.sh
```

After the file changes, restart the Codex or Claude session so the client
reloads the MCP config and current bearer token.

If you only want to patch `.mcp.json` without running the probes:

```bash
PCG_SKIP_PROBES=true ./scripts/sync_local_compose_mcp.sh
```

### Health and pipeline status

Replace `localhost:8080` with the appropriate host and port if using
overrides.

```bash
# Health probes
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/readyz

# Pipeline summary (scopes, facts, work items, failures)
curl -s http://localhost:8080/admin/status | jq .

# Content store stats
curl -s http://localhost:8080/api/v0/content/stats | jq .

# Query the graph for repositories
curl -s http://localhost:8080/api/v0/repositories | jq .

# Query relationships (if any were built)
curl -s 'http://localhost:8080/api/v0/query' \
  -H 'Content-Type: application/json' \
  -d '{"query": "MATCH (n)-[r]->(m) RETURN labels(n)[0] AS from_type, type(r) AS rel, labels(m)[0] AS to_type, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"}' \
  | jq .
```

## Docs And Hygiene

Before calling a change ready:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```
