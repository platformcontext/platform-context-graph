# ADR: Neo4j Parity Optimization Plan

**Date:** 2026-05-04
**Status:** In progress
**Authors:** Allen Sanabria
**Deciders:** Platform Engineering

## Decision

NornicDB is PCG's officially supported graph database and remains the promoted
default. Neo4j is an alternative for teams that already operate Neo4j, but it
must earn that position by running PCG's shared Cypher/Bolt contract without a
parallel writer stack.

PCG will keep graph support open to future Cypher/Bolt databases, but only when
they support the raw Cypher calls PCG already owns, or require small,
evidence-backed adapter seams. The allowed seams are narrow: schema DDL,
connection/runtime settings, retry classification, and query-builder details
where the shared contract cannot express a real backend difference. PCG should
not carry one writer stream for NornicDB and another writer stream for every
other graph product.

This ADR is therefore a parity and conformance workstream. It records whether
Neo4j can follow the same shared path that makes NornicDB fast enough for the
full-corpus lane. If it cannot, the decision should be explicit:
compatibility-only Neo4j, or NornicDB-only until another database proves the
same contract.

## Current Evidence

NornicDB has a completed production-profile proof:
`pcg-full-pr138-a2c630af-b68b4ef-20260504T120630Z` rebuilt PCG `a2c630af`
with NornicDB latest `main` `b68b4ef`, indexed the full corpus, drained
`8458/8458` queue rows in `878s`, kept retrying, failed, and dead-letter rows
at `0`, and passed API/MCP relationship-evidence drilldowns.

Neo4j does not yet have a terminal comparison. The stopped run
`pcg-neo4j-baseline-pr138-a2c630af-20260504T123656Z` was still clean at
`1946s` (`0` retrying, failed, or dead-letter rows), but only `553/896`
source-local projector items had succeeded. That means the first parity target
is probably source-local canonical projection, not reducer truth or API/MCP
read correctness. This is an inference from the stopped run, not a proven root
cause.

The current branch repeated a bounded Neo4j baseline after adding grouped
statement metrics: `pcg-neo4j-baseline-pr140-6b44dfe5-20260504T143040Z`
rebuilt PCG `6b44dfe5` and stopped at `2026-05-04T14:51:26Z`, roughly twenty
minutes after start. It stayed clean (`0` retrying, failed, and dead-letter
rows), but source-local projection had only `395` successes with `493` still
pending, `5` running, and `3` claimed. Reducer work was not the blocker at that
point: `3008` reducer rows had succeeded and only `3` reducer rows were still
pending. The canonical write log showed `395` completed canonical writes with
`8727.087s` summed write time, `22.094s` average, and `651.698s` max for a
single repository. Neo4j was busy during the snapshot, not idle: the container
reported about `802%` CPU, about `9.2GiB` memory, and low block read pressure.
This bounded run did not reach API/MCP truth because the graph never drained.

The first focused slice then tried the most obvious transaction-shape change:
`pcg-neo4j-phasegroups-pr140-d97ad213-20260504T150142Z` rebuilt PCG
`d97ad213` and enabled `PCG_NEO4J_CANONICAL_PHASE_GROUPS=true` with
`PCG_NEO4J_PHASE_GROUP_STATEMENTS=100` in the branch experiment. The path was
active and produced `canonical phase group completed` logs, but it did not
improve slope. At the ten-minute sample it had `256` source-local successes
with `632` pending, `6` running, and `2` claimed; the atomic bounded baseline
was already at `288` source-local successes around the same point. The run
stayed clean (`0` retrying, failed, or dead-letter rows), but the slow phases
were still `entity_containment` and `entities`; the largest observed phase was
`entity_containment` at `292.874s` for `573` statements. This rejects broad
Neo4j phase grouping at the `100`-statement cap as the first parity fix, and
the product code no longer keeps those Neo4j-only knobs.

The first chunk of this ADR is to collect enough Neo4j-specific evidence to
separate:

- source-local canonical write time
- reducer graph-write time
- queue wait and claim/fencing effects
- driver transaction overhead
- Neo4j lock/deadlock/retry behavior
- graph read/query plan costs
- API/MCP truth after the graph has drained

## External Constraints

Neo4j's own documentation shapes the research plan:

- Neo4j recommends batching large writes with `UNWIND` and parameters, and
  warns that repeated single-row writes are an anti-pattern:
  <https://neo4j.com/docs/go-manual/current/performance/#performance-recommendations-batch-data-creation>
- Query parameters help the database query cache and avoid dynamic Cypher text:
  <https://neo4j.com/docs/go-manual/current/performance/#performance-recommendations-use-query-parameters>
- `MERGE` is convenient but can require a match before create; Neo4j recommends
  `CREATE` when the data is known to be new:
  <https://neo4j.com/docs/go-manual/current/performance/#performance-recommendations-use-merge-for-creation-only-when-needed>
- Neo4j documents deadlocks and lock-order concerns around concurrent writes,
  including `MERGE` lock behavior and the need for bounded retries:
  <https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/>
- Neo4j indexes are the planner access path for exact-match reads and writes,
  so parity work must confirm that every hot `MATCH` / `MERGE` identity has a
  supporting constraint or search-performance index:
  <https://neo4j.com/docs/cypher-manual/current/indexes/>

## Current PCG Flow

The path we need to compare is:

```text
sync -> discover -> parse -> emit facts -> enqueue source-local work
-> projector canonical writes -> reducer shared writes -> API/MCP reads
```

Relevant ownership seams:

- `go/internal/storage/cypher/` owns backend-neutral statements, canonical
  node/edge writers, semantic writers, retry wrappers, timeout wrappers, and
  graph-write telemetry.
- `go/cmd/ingester/wiring_neo4j_executor.go` and
  `go/cmd/bootstrap-index/wiring.go` own current Neo4j/Bolt write sessions for
  source-local and bootstrap writes.
- `go/cmd/ingester/wiring_nornicdb_phase_group.go` owns the NornicDB
  phase-group executor that made canonical writes measurable by phase.
- `go/cmd/reducer/main.go` selects graph-backend-specific writer modes.
- `go/cmd/reducer/config.go` sets different worker, claim-window,
  projector-drain, and semantic-claim defaults for NornicDB versus Neo4j.
- `go/internal/query/code_call_chain.go`,
  `go/internal/query/code_call_chain_nornicdb.go`, and
  `go/internal/query/code_relationships.go` contain backend-aware read/query
  shapes that must stay behind query-builder seams.

## Code-Path Inventory

This first read found that PCG does not have a thick Neo4j implementation in
`go/internal/storage/neo4j`. The Neo4j package is currently documentation and
package ownership; live Bolt write behavior is wired through command/runtime
adapters, while the durable statement shapes live in `go/internal/storage/cypher`.
That means the parity work should harden the shared Cypher writer/executor seam
first, not create a second graph stack.

Current differences:

| Area | Current NornicDB path | Current Neo4j path | Initial classification |
| --- | --- | --- | --- |
| Canonical execution | Bounded phase-group execution with per-phase chunks. | `GroupExecutor` usually runs one atomic canonical group. | Parity candidate: broad phase grouping was tested and rejected as a first fix. Continue only if a narrower shared contract needs bounded execution. |
| Canonical row caps | File, entity, label, and containment caps are backend-aware. | Mostly generic `PCG_NEO4J_BATCH_SIZE`. | Conformance candidate: prefer shared row-shape improvements; add backend-specific caps only for a proven minor runtime constraint. |
| Entity containment | NornicDB uses file-scoped inline containment by default and keeps the batched-across-files switch as a latest-main experiment. | Neo4j now uses the same file-scoped inline containment writer mode through ingester and bootstrap wiring. | Current target: prove the shared containment contract with focused Neo4j and NornicDB runs before moving up the corpus ladder. |
| Semantic entities | NornicDB uses canonical-node enrichment and label-scoped retract modes. | Neo4j stays on the legacy semantic writer path. | Parity candidate: test whether the shared canonical-node mode should become the only production path, with backend-specific seams only where required. |
| Queue/concurrency | NornicDB defaults to tighter claim windows and semantic claim limit `1`. | Neo4j claims up to `workers*4` and has no semantic claim limit by default. | Parity candidate: profile lock waits, retry counts, and queue wait before changing defaults. |
| Schema/indexes | NornicDB adds explicit hot lookup indexes and schema dialect translations. | Neo4j relies on constraints and its planner. | Research required: confirm hot `MATCH` and `MERGE` anchors use indexes in Neo4j. |
| Reads | NornicDB has custom call-chain, relationship, and dead-code query builders. | Neo4j keeps the older `shortestPath`, map-collection, and negative-pattern forms. | Mostly a gap only if API/MCP reads are slow after writes drain; measure after baseline. |
| Timeouts/retries | NornicDB has graph-write transaction deadlines and extra retry classifications. | Neo4j keeps Neo4j transient/deadlock retry behavior without the same write budget. | Design gap only if evidence shows unbounded waits, deadlocks, or transaction slope. |
| Telemetry | NornicDB has phase, label, chunk, statement, and duration logs. | Neo4j shares generic graph metrics but lacks matching per-phase detail. | First implementation candidate: mirror evidence before tuning behavior. |

The first code slice is diagnostic, not behavioral: expose Neo4j canonical and
semantic write timing with the same phase/label vocabulary used to understand
NornicDB. After that, decide whether the next change belongs in the shared
Cypher contract, schema/index coverage, semantic writer mode, queue/concurrency,
or query shape.

## Suspected Parity Gaps

These are hypotheses until measured:

| Area | Current signal | Research question |
| --- | --- | --- |
| Canonical write grouping | NornicDB has bounded phase groups and phase/label logs; Neo4j usually uses `GroupExecutor` atomic groups or default batches. | Broad Neo4j phase grouping was not the fix. Does a narrower shared transaction boundary still matter, or is the bottleneck inside the statement shape itself? |
| Canonical entity/file shape | NornicDB has file/entity batch sizes, label caps, and entity-containment modes. | Does the shared entity/file Cypher contract give every supported backend a selective anchor and bounded relationship-existence check? |
| Semantic writer mode | NornicDB uses merge-first/canonical-node writer modes and label caps. | Should the canonical-node path become the common production path for all supported graph backends? |
| Queue and concurrency | NornicDB uses bounded worker defaults, claim windows near workers, source-local drain gating, and semantic claim limit `1`. | Is Neo4j slow because of too much concurrency, too little concurrency, broad claim windows, or graph locks? |
| Schema/index parity | NornicDB needed explicit lookup indexes for hot labels. | Are Neo4j constraints/indexes sufficient for PCG's exact hot anchors, or do some read/write shapes miss planner indexes? |
| Read/query shapes | NornicDB has custom call-chain and relationship traversal builders. | Do Neo4j API/MCP reads need `EXPLAIN`/`PROFILE` coverage and narrower anchors, or are writes the only blocker? |
| Observability | NornicDB phase-group logging names phase, label, rows, statements, grouped executions, total duration, and max execution. | Does Neo4j have equivalent per-phase, per-label, transaction, retry, and lock-wait evidence before tuning? |

## Research Chunks

| Chunk | Status | Output |
| --- | --- | --- |
| 1. Code-path inventory | Complete | Neo4j mostly uses runtime Bolt wiring plus shared `storage/cypher` writers; NornicDB has additional phase grouping, writer modes, caps, and logs. The inventory above marks parity candidates versus backend-specific design choices. |
| 2. Neo4j baseline instrumentation | Complete | Current branch adds phase metadata to atomic canonical statements and records Neo4j grouped batch metrics per statement, including `write_phase` and `node_type` where available. The reducer `/metrics` scrape proved the Neo4j batch metrics are emitted. Bootstrap source-local projection still needs log-based timing because `bootstrap-index` has no `/metrics` HTTP surface. |
| 3. Terminal or bounded Neo4j baseline | Complete | Bounded run `pcg-neo4j-baseline-pr140-6b44dfe5-20260504T143040Z` stayed clean but was far off the NornicDB pace: after about twenty minutes, source-local projection was `395` succeeded with `501` still open, while reducer rows were almost caught up. API/MCP proof did not run because the graph did not drain. |
| 4. Hypothesis ranking | Complete | First target is source-local canonical write shape. The evidence points away from reducer scheduling, API/MCP reads, and host idleness. Broad phase grouping was the first tested hypothesis because it was the closest analogue to the NornicDB fast path. |
| 5. Focused implementation slice: broad phase grouping | Complete / rejected | Remote run `pcg-neo4j-phasegroups-pr140-d97ad213-20260504T150142Z` proved the experimental path worked but did not improve slope at the `100`-statement cap. The Neo4j-only knobs and executor were removed so PCG does not keep a second product-specific writer stream for a rejected hypothesis. |
| 6. Focused implementation slice: entity-containment write shape | Complete / partial win | Current branch adds file/entity/`CONTAINS` coverage to the shared live backend conformance corpus and runs it twice before readback to prove idempotency. Ingester and bootstrap wiring now put Neo4j on the same file-scoped inline entity containment writer mode already used by NornicDB, while keeping the NornicDB batched-across-files switch as an explicit latest-main experiment. Local unit proof and local live NornicDB/Neo4j conformance passed. Remote Neo4j run `pcg-neo4j-inline-containment-20260504T165156Z` stayed clean but was not acceptance-fast: around the twenty-minute mark it had `549` source-local successes with `339` still pending, and by the stopped sample it had `662` source-local successes with `226` pending. The separate `entity_containment` phase was gone, but large Neo4j canonical atomic transactions remained the wall: top observed writes included `979` statements in `555.484s`, `498` statements in `536.743s`, and `1176` statements in `499.767s`. A follow-up bounded phase-group experiment, `pcg-neo4j-bounded-inline-20260504T172932Z`, was stopped early and not kept because the early slope was slightly worse (`269` source-local successes at the comparable window versus `277` for inline-only). |
| 7. Proof ladder | Started / blocked on next fix | The first remote Neo4j full-corpus proof for this slice was intentionally stopped before API/MCP proof because source-local did not drain near the target envelope. The next proof ladder should start only after a new measured fix addresses large Neo4j canonical atomic transactions; otherwise it will repeat the same slow source-local wall. |

## Acceptance Bar

Neo4j parity work is ready for promotion only when:

- Neo4j drains the same full corpus from a fresh rebuild with `0` failed and
  dead-letter rows.
- API and MCP truth checks pass after drain.
- Evidence identifies the bottleneck moved or was removed.
- The implementation stays in documented adapter seams.
- NornicDB performance and correctness do not regress.
- The final ADR update records wall time, queue state, host stats, phase sums,
  retry/deadlock counts, and query truth.
- The implementation still runs through the shared PCG Cypher contract, with no
  alternate Neo4j writer stream.

The target should be set before implementation after the terminal baseline.
The initial product bar is: Neo4j cannot remain night-and-day slower than
NornicDB if PCG calls both production-promoted.

## Non-Goals

- Do not deprecate Neo4j in this ADR.
- Do not mark Neo4j compatibility-only before the parity research is complete.
- Do not add handler-level forks.
- Do not add support for arbitrary Bolt/Cypher databases without conformance
  and performance evidence.
- Do not tune by raising global timeouts, shrinking batches blindly, or turning
  worker defaults down without root-cause proof.
