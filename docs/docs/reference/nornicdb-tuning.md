# NornicDB Tuning Reference

This page is the operator map for PCG's NornicDB-specific environment
variables. Use it when `local_authoritative` indexing is correct but a
repo-scale run exposes a bounded write timeout, slow phase, or compatibility
gate.

For the complete PCG environment-variable catalog, including non-NornicDB
collector, queue, database, telemetry, and Compose settings, see
[Environment Variables](environment-variables.md).

NornicDB is still a candidate graph backend. Tune from evidence: first identify
the phase, label, row count, grouped statement count, and timeout shape in the
structured logs, then change the narrowest matching knob. Do not lower broad
defaults because one chunk looked scary.

## Backend Selection

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `PCG_GRAPH_BACKEND` | `neo4j` | API, MCP, ingester, reducer, local host | Set to `nornicdb` to opt into the NornicDB adapter. Invalid values fail startup. |
| `PCG_NORNICDB_BINARY` | unset | local host / install / tests | Points PCG at an explicit NornicDB binary. This wins over managed `${PCG_HOME}/bin/nornicdb-headless` and `PATH`. |
| `PCG_NORNICDB_INSTALL_TIMEOUT` | `30s` | `pcg install nornicdb` | Extends remote download timeouts for slow links. |

## Canonical Write Budget

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `PCG_CANONICAL_WRITE_TIMEOUT` | `30s` on NornicDB | ingester, reducer graph writers | Bounds each NornicDB graph execution with a client deadline and Bolt transaction timeout. Shorten for diagnostics; lengthen only with evidence. |
| `PCG_NORNICDB_PHASE_GROUP_STATEMENTS` | `500` | canonical writes | Broad grouped-statement cap for phases without a narrower phase-specific cap. |
| `PCG_NORNICDB_FILE_PHASE_GROUP_STATEMENTS` | `5` | canonical `files` phase | Limits how many file-upsert statements share one grouped Bolt transaction. |
| `PCG_NORNICDB_FILE_BATCH_SIZE` | `100` | canonical `files` phase | Limits rows inside each `phase=files` statement. Use when file groups are narrow but one statement still carries too many rows. |
| `PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS` | `25` | canonical `entities` and `entity_containment` phases | Limits grouped statement count for canonical entity phases. |
| `PCG_NORNICDB_ENTITY_BATCH_SIZE` | `100` | canonical entity rows | Limits rows inside normal entity upsert statements before label-specific caps apply. |
| `PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES` | `Function=15,K8sResource=1,Struct=50,Variable=10` | canonical entity rows | Overrides row caps for specific canonical labels, for example `Function=15,Variable=10`. |
| `PCG_NORNICDB_ENTITY_LABEL_PHASE_GROUP_STATEMENTS` | `Function=5,K8sResource=1,Struct=15,Variable=5` | canonical entity grouping | Overrides grouped-statement caps for specific canonical labels. |

Two knobs often look similar but are different:

- `*_PHASE_GROUP_STATEMENTS` controls how many statements run in one grouped
  transaction.
- `*_BATCH_SIZE` controls how many rows are inside one statement.

Use the timeout summary and `nornicdb entity label summary` logs to decide
which dimension failed.

PCG applies `PCG_CANONICAL_WRITE_TIMEOUT` in two places on NornicDB: the
client context deadline and the Neo4j-driver Bolt `tx_timeout` metadata. Keep
both sides aligned so a timed-out reducer or ingester write does not merely
stop waiting while the database keeps executing the same mutation.

When that budget is exhausted, PCG stores the queue failure as
`graph_write_timeout` and preserves the sanitized phase/label/row summary in
`failure_details`. Timeout failures are intentionally not retried just because
they are timeouts; only proven transient conflict errors opt into bounded retry.

## Semantic Write Budget

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES` | `Annotation=10,Function=10,ImplBlock=10,Module=10,Variable=10` | reducer semantic entity materialization | Overrides NornicDB row caps for semantic labels after parser-enriched semantic metadata proves expensive. |
| `PCG_REDUCER_WORKERS` | `1` on NornicDB | reducer graph writers | Overrides reducer work concurrency. Leave unset for normal NornicDB runs; raise only when intentionally testing graph-write contention. |
| `PCG_REDUCER_BATCH_CLAIM_SIZE` | `1` on NornicDB | reducer queue claim window | Limits how many reducer intents one claim cycle leases before workers start them. Keep this near worker count when raising reducer workers so queued-but-not-started items do not expire their leases. |
| `PCG_CODE_CALL_PROJECTION_ACCEPTANCE_SCAN_LIMIT` | `250000` | reducer code-call projection | Bounds how many code-call shared intents one accepted repo/run may scan or load before failing safely. Raise only when a real repo has more CALLS intents than the default and memory headroom is known. |

Semantic materialization is a reducer-owned phase. Do not copy canonical caps
blindly; semantic labels should be narrowed only after timeout summaries name
the semantic label and row count.

Code-call projection is also reducer-owned, but its scan limit is a correctness
guard rather than a graph-write tuning knob. The runner retracts repo-wide
CALLS edges and then rewrites the accepted repo/run slice, so it must load the
whole acceptance unit before marking intents complete. If
`PCG_CODE_CALL_PROJECTION_ACCEPTANCE_SCAN_LIMIT` is exhausted, use the
discovery advisory report first to confirm the repo is not dominated by
generated or vendored code before raising the limit.

Increase `PCG_CODE_CALL_PROJECTION_ACCEPTANCE_SCAN_LIMIT` only when all of the
following are true:

- The reducer log names `code call acceptance scan reached cap` or
  `code call acceptance intent scan reached cap`.
- The discovery advisory shows the repo's high code-call volume comes from
  authored source you intentionally want in the graph, not checked-in bundles,
  generated output, archives, or third-party vendor trees that should be
  filtered with `.pcg/discovery.json`.
- The host has memory headroom for loading the full accepted repo/run slice in
  one reducer cycle. The guard exists to prevent partial CALLS truth, not to
  make unbounded in-memory projection safe.

Do not increase it for `graph_write_timeout`, slow canonical phases, semantic
label timeouts, or queue backlog by itself. Those failures belong to the
phase/label/write-shape controls above, the discovery advisory workflow, or a
deeper reducer/code-call projection design change. If a real authored repo
needs more than the default repeatedly, record the advisory evidence and
consider redesigning code-call projection to page a complete acceptance unit
safely instead of growing the cap indefinitely.

When `PCG_GRAPH_BACKEND=nornicdb`, PCG defaults reducer intent execution to one
worker because reducer domains can independently mutate the same graph sidecar.
This does not serialize source discovery, parsing, source-local projection, or
unrelated local-host processes; it only removes unsafe overlap between reducer
graph writes unless an operator explicitly sets `PCG_REDUCER_WORKERS`.
NornicDB also narrows the reducer batch-claim window to one item by default.
That preserves useful worker concurrency when `PCG_REDUCER_WORKERS` is raised
without pre-leasing many slow graph-write items that can sit in the local worker
channel until their `claim_until` expires and the status panel reports overdue
claims.

For `PCG_QUERY_PROFILE=local_authoritative` plus `PCG_GRAPH_BACKEND=nornicdb`,
reducer claims also wait while source-local projector work is outstanding. This
is not a row-size tuning knob: it removes the unsafe overlap where
first-generation canonical projection and reducer graph writes contend for the same
embedded NornicDB sidecar. Neo4j keeps the existing production concurrency path,
and NornicDB operators can still raise reducer workers for controlled
experiments after source-local projection has drained.

First-generation semantic materialization skips stale retract because there is
no prior semantic graph state to clean up. Refreshes and retries still retract;
on NornicDB those retracts run one semantic label per statement. The Neo4j
adapter keeps its broad multi-label retract, but NornicDB's syntax and cost
profile make the label-scoped shape the safer repo-scale cleanup path.

## Compatibility And Conformance Switches

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `PCG_NORNICDB_CANONICAL_GROUPED_WRITES` | unset / `false` | canonical writes | Conformance-only switch that exposes Neo4j-style grouped canonical writes on NornicDB. Leave unset for normal laptop runs. |
| `PCG_NORNICDB_REQUIRE_GROUPED_ROLLBACK` | unset / `false` | test gates | Makes rollback conformance mandatory in opt-in NornicDB grouped-write tests. |
| `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT` | unset / `false` | canonical entity writes | Patched-binary evaluation switch for cross-file batched entity containment. Leave off for the pinned release-backed binary unless the ADR says the binary supports the required row-safe hot path. |

## NornicDB Runtime Diagnostics

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `NORNICDB_ENABLE_PPROF` | unset / `false` | NornicDB process | Enables NornicDB profiling when a run is progressing linearly and PCG logs no longer identify a PCG-side batching mistake. |

## Adding New Knobs

Phase-specific tuning is deliberately narrow and evidence-driven. Before
adding another `PCG_NORNICDB_*` variable:

1. Capture a timeout or slow-phase log that names the phase, label, row count,
   grouped statement count, and duration.
2. Prove whether the failure is statement width, row width, query shape,
   missing NornicDB functionality, or machine/resource pressure.
3. Prefer fixing NornicDB when PCG is missing a Neo4j-equivalent primitive and
   the feature belongs in the database.
4. Add the narrowest PCG adapter seam only when the evidence shows a PCG-side
   shape or bounded budget is the right fix.
5. Update this page, the active NornicDB ADR, and the local testing runbook in
   the same PR.

If a one-row or very-low-row statement is still slow, do not immediately lower
global graph-write concurrency. First confirm whether NornicDB is taking the
intended hot path or falling back to a generic executor. The compatibility
workflow prefers adding performant NornicDB support for Neo4j-equivalent query
shapes before PCG gives up useful cross-repo parallelism.
For canonical entity writes, ordinary one-row file-scoped batches should still
use the `UNWIND $rows AS row` hot path. The execute-only singleton fallback is
reserved for rows containing the known `shortestPath` / `allShortestPaths`
parser hazard; broad singleton logs for normal symbols usually mean a writer
shape regression, not a reason to lower global concurrency.
If a correctly grouped `MERGE (n:<Label> {uid: row.entity_id})` statement is
still slow at one row, check schema preconditions before tuning workers:
NornicDB needs the matching `<Label>.uid` uniqueness constraint to use its
schema-backed merge lookup instead of a generic label scan.
File-phase writes have the same rule. PCG's NornicDB schema includes explicit
property indexes for `Repository.id`, `Directory.path`, and `File.path` because
NornicDB's `MERGE` lookup path checks property indexes before falling back to a
label scan. If `phase=files` chunks grow steadily slower as the graph grows,
verify these indexes were created before changing file batch sizes or write
timeouts.

Watch future heavy write families such as call edges, infra edges, and other
shared reducer domains. If they need different treatment, add phase metadata
and tuning only after repo-scale evidence proves the existing canonical or
semantic controls do not describe the bottleneck.
