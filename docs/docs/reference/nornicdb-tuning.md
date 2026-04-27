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

## Validation Ladder

Do not use the full corpus as the first debugging loop for a timeout. When a
run names a specific repo, scope, phase, label, and row count, validate in this
order:

1. Re-run only the failing repo with a fresh `PCG_HOME`, rebuilt PCG binaries,
   and the exact NornicDB binary under evaluation.
2. If the timeout is the only blocker and the statement is plausibly correct,
   raise `PCG_CANONICAL_WRITE_TIMEOUT` for that correctness-validation lane
   (for example `120s`) so the pipeline can finish and reveal later semantic or
   query-truth failures.
3. After the single repo drains with `pending=0`, `in_flight=0`, and no
   dead letters, run a medium corpus of 15-20 representative repos.
4. Run the full corpus only after the focused and medium lanes pass end to end.

This ladder separates correctness from performance. A larger timeout is allowed
to prove the graph, queue, and query surfaces finish correctly; it must not be
treated as the final tuning answer without later phase timing and write-shape
analysis.

Latest checkpoint: PCG `f72724d6` with NornicDB `86e78f1` passed the 2026-04-27
focused self-repo lane and the `/home/ubuntu/pcg-test-repos` medium lane after
switching the NornicDB semantic writer to the merge-first explicit-row shape.
The medium run covered `23` repos, drained healthy in `316s`, ended with queue
`pending=0 in_flight=0 retrying=0 dead_letter=0 failed=0`, and logged no
`graph_write_timeout`, semantic failure, acceptance-cap, panic, fatal, or
dead-letter lines. Treat that as the current focused/medium correctness proof;
the next promotion evidence must come from a DB-driven full-corpus drain.

Follow-up checkpoint: PCG `c598000d` then passed a targeted five-repo lane that
combined the prior small semantic regressions with the two noisy PHP stress
repos. It drained healthy in `854s`; the largest projections were
`api-php-sample-appwebsolutions` at `148,948` facts in `166.496305644s` and
`websites-php-youboat` at `176,201` facts in `521.49982913s`; their semantic
reducers completed in `6.33473887s` and `15.762956452s`; and the run ended
with `pending=0 in_flight=0 retrying=0 dead_letter=0 failed=0`. Use this as
the current problem-repo proof before moving to a larger representative subset.

Representative subset checkpoint: PCG `5c9b169a` with the same NornicDB
`86e78f1` binary drained a 50-repo subset from `/home/ubuntu/pcg-e2e-full` in
`884s` with final `Health: healthy` and queue
`pending=0 in_flight=0 retrying=0 dead_letter=0 failed=0`. The log scan found
no graph write timeout, semantic failure, acceptance-cap, retry, dead-letter,
panic, or fatal lines. The slow path was not reducer semantic correctness:
`websites-php-youboat` source-local projection held the queue while writing
`131,977` `Variable` entities and `28,926` `Function` entities. During that
phase, `Variable` entity chunks progressed from small subsecond executions to
a label summary of `102,654` rows, `13,200` statements, and `130.161796981s`
total label time before the repo drained. Treat this as the current evidence
that the remaining performance target is high-cardinality source-local
canonical entity writes and noisy repo input shape, not another semantic
batch-cap tweak.

Patched-binary batched-containment checkpoint: a 2026-04-27 isolated
`websites-php-youboat` rerun on PCG `dcb5e466` with
`PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true`, `PCG_CANONICAL_WRITE_TIMEOUT=120s`,
`PCG_REDUCER_WORKERS=2`, and the `#119 + #120` NornicDB binary drained the
main queue cleanly with no graph timeout, retry, dead-letter, panic, or fatal
lines. The repo discovered `74,475` files and persisted `176,201` facts;
collection/emission took `161.706108907s`. Source-local projection reached
`Variable=131,977`, `Function=28,926`, `Class=6`; canonical `Variable` used
the intended `batch_across_files=true` shape and completed `131,977` rows as
`13,198` statements / `2,640` grouped executions in `301.798956955s` with no
singleton fallbacks. This validates the patched-binary switch for correctness
on the noisy repo, but it is still not a default-path promotion: canonical
`files` chunks and later `Variable` executions still showed graph-size slope,
so the next optimization target is NornicDB file-anchor and relationship
existence lookup behavior before adding more PCG batch caps.

Variable row-cap checkpoint: follow-up 2026-04-27 focused reruns on
`websites-php-youboat` showed the earlier narrow `Variable=10` default was too
conservative after file-scoped entity batching. The same `131,977` canonical
`Variable` rows completed in `196.713s` at `10` rows, `130.082s` at `25`,
`118.136s` at `50`, and `102.820s` at `100`, with zero singleton fallbacks,
zero retries, zero dead letters, and max grouped execution `0.607s` at the
`100`-row cap. A small control run on `terraform-module-karpenter` also
drained healthy with queue `pending=0 in_flight=0 retrying=0 dead_letter=0
failed=0`. This promotes `Variable=100` as the built-in default. Raise beyond
`100` only after a focused run shows max grouped execution remains comfortably
below `PCG_CANONICAL_WRITE_TIMEOUT`; lower it again only if timeout summaries
name `Variable` and the discovery advisory confirms the rows are authored
source that should remain in the graph.

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
| `PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES` | `Function=15,K8sResource=1,Struct=50,Variable=100` | canonical entity rows | Overrides row caps for specific canonical labels, for example `Function=15,Variable=100`. |
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
`failure_details`. Typed graph write timeouts are bounded-retry candidates: the
first timeout can be transient backend pressure or graph-write contention, but
the queue still dead-letters after the configured attempt budget. Deterministic
syntax, schema, and unsupported-query failures remain terminal because they do
not implement the retry contract.

## Semantic Write Budget

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES` | `Annotation=5,Function=10,ImplBlock=10,Module=10,TypeAlias=5,TypeAnnotation=50,Variable=10` | reducer semantic entity materialization | Overrides NornicDB row caps for semantic labels after parser-enriched semantic metadata proves expensive. |
| `PCG_REDUCER_WORKERS` | `min(NumCPU, 8)` on NornicDB | reducer graph writers | Overrides reducer work concurrency. Leave unset for normal NornicDB runs; lower only when conflict-domain fencing still shows graph write conflicts or backend saturation. |
| `PCG_REDUCER_BATCH_CLAIM_SIZE` | `workers` on NornicDB | reducer queue claim window | Limits how many reducer intents one claim cycle leases before workers start them. Keep this near worker count so queued-but-not-started items do not expire their leases. |
| `PCG_CODE_CALL_PROJECTION_ACCEPTANCE_SCAN_LIMIT` | `250000` | reducer code-call projection | Bounds how many code-call shared intents one accepted repo/run may scan or load before failing safely. Raise only when a real repo has more CALLS intents than the default and memory headroom is known. |

Semantic materialization is a reducer-owned phase. Do not copy canonical caps
blindly; semantic labels should be narrowed only after timeout summaries name
the semantic label and row count.

NornicDB semantic writes use a merge-first explicit row template instead of the
older `MATCH File` before `MERGE node` row-map shape. The older shape can still
use schema lookup, but trace probes showed it misses NornicDB's generalized
`UNWIND/MERGE` batch hot path. Treat semantic timeouts as query-shape evidence
first, then tune label caps only after confirming the statement is already on
the intended template. The merge-first writer is currently validated through the
focused and medium lanes above; a full-corpus timeout in this phase should be
treated as new evidence and narrowed to the label, row count, graph size, and
query shape before changing caps.

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

When `PCG_GRAPH_BACKEND=nornicdb`, PCG defaults reducer intent execution to a
bounded CPU-sized worker pool and relies on durable conflict-domain keys for
safety. Code-graph reducer domains for one repo serialize with one another,
platform graph reducer domains for that repo serialize with one another, and
unrelated families can still run concurrently. The claim window defaults to the
worker count so each claimed item can enter heartbeat-protected execution
promptly instead of sitting in the local worker channel until `claim_until`
expires.

For `PCG_QUERY_PROFILE=local_authoritative` plus `PCG_GRAPH_BACKEND=nornicdb`,
reducer claims also wait while source-local projector work is outstanding. This
is not a row-size tuning knob: it removes the unsafe overlap where
first-generation canonical projection and reducer graph writes contend for the
same embedded NornicDB sidecar. Neo4j keeps the existing production concurrency
path, and NornicDB operators should tune worker count only from post-drain
queue tail, graph-write timeout, CPU, disk, and NornicDB profile evidence.

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
