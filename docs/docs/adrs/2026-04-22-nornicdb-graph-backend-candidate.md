# ADR: NornicDB As Candidate Graph Backend

**Date:** 2026-04-22
**Status:** Proposed (provisional)
**Authors:** Allen Sanabria
**Deciders:** Platform Engineering
**Related:**

- `docs/docs/adrs/2026-04-20-embedded-local-backends-desktop-mode.md`
- `docs/docs/adrs/2026-04-20-embedded-local-backends-implementation-plan.md`
- `docs/docs/reference/capability-conformance-spec.md`
- `docs/docs/reference/truth-label-protocol.md`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/local-host-lifecycle.md`
- `docs/docs/reference/local-performance-envelope.md`
- `docs/docs/reference/graph-backend-installation.md`
- `docs/docs/reference/graph-backend-operations.md`

---

## Evaluation Status

| Phase | Status | Evidence | Remaining |
| --- | --- | --- | --- |
| Profile/backend admission | In progress | `0e4d8a5f`, current branch local-host profile/backend gating, current branch loopback-TCP sidecar lifecycle and shared Bolt-driver path, manual smoke with `/tmp/nornicdb-headless` showing healthy owner + clean Ctrl-C shutdown; `575ca864` added `TestNornicDBSyntaxVerification` and `TestNornicDBCompatibilityWorkarounds`; `5f5a781e` added schema-dialect routing and `TestNornicDBSchemaAdapterVerification`; current branch managed-install discovery prefers `${PCG_HOME}/bin/nornicdb-headless` after explicit env override; 2026-04-22 temporary-home smoke proved local_authoritative start/status/logs/stop with NornicDB; 2026-04-23 MCP smoke proved content-index-backed `search_file_content` and `find_code` continue to work while canonical graph projection degrades on a bounded NornicDB write timeout; current branch lets `pcg install nornicdb --from <source>` consume local binaries, local tar archives, and URLs without yet inventing a no-arg release selector | pinned no-arg installer, signature policy, perf smoke |
| Operator CLI surface | In progress | `da35d729`, current branch `pcg graph status`; current branch `pcg install nornicdb --from <source> [--sha256 <hex>] [--force]` verifies and installs a local binary, local archive, or URL-backed archive; current branch `pcg graph logs`; current branch owner-aware `pcg graph stop`; current branch foreground `pcg graph start`; current branch stopped-owner `pcg graph upgrade --from <source>`; 2026-04-22 smoke proved install → start → status running → logs → stop → status stopped | pinned release download/signature installer and perf smoke |
| Adapter conformance | In progress | current branch routes NornicDB canonical writes through sequential execute-only writes by default, applies Bolt `tx_timeout` metadata plus client context deadlines, preserves production Neo4j grouped writes, and adds the explicit `PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` conformance switch for proving NornicDB grouped writes; 2026-04-23 rebuilt linuxdynasty-fork headless binary `/tmp/nornicdb-headless-pcg-rollback` (`v1.0.42-hotfix`) passed `TestNornicDBGroupedWriteSafetyProbe` and strict `TestNornicDBGroupedWriteRollbackConformance`: PCG repository/file/function grouped commit succeeded, grouped rollback marker count `0`, clean explicit rollback marker count `0`, failed-statement explicit rollback marker count `0`, and timeout probe left no partial write | release-backed fixed NornicDB binary, full `GraphQuery`/`GraphWrite` adapter, matrix runs |
| Performance + promotion gates | Not started | — | laptop perf smoke, Compose conformance, production-scale comparison |

## Context

PCG's authoritative graph backend is Neo4j. That choice is load-bearing for
production correctness and for the full-stack Compose profile, but it carries
three material costs:

- JVM footprint and ops surface that is heavy relative to the rest of the PCG
  runtime.
- License model (Neo4j Community GPLv3, commercial Enterprise) that constrains
  downstream packaging.
- Runtime shape that is Docker- or Kubernetes-first, which is a friction point
  for developers who want a laptop-native authoritative graph experience
  without running Compose.

PCG lightweight local mode was the first response: ship embedded Postgres with
relational code-intelligence tables and refuse high-authority graph queries
via structured `unsupported_capability`. That is correct for the
"single-binary, no extra services" promise, but it leaves a gap:

- Developers cannot run transitive caller analysis, call-chain path queries,
  or dead-code detection locally without Compose.
- That same gap means we cannot dogfood graph-backed code intelligence
  against the PCG repository itself on a plain laptop.

The capability-port decomposition (ADR 2026-04-20 §5) already made swapping
graph backends a wiring concern rather than a code-rewrite. That opens the
door to evaluating an alternative graph backend without reopening handler-level
contracts.

## Candidate: NornicDB

NornicDB is a pure-Go graph database (module `github.com/orneryd/nornicdb`,
MIT licensed) that speaks Neo4j Bolt + Cypher. Storage is Badger v4 (pure-Go
LSM KV). It ships as a standalone binary / Docker image, not as an in-process
Go library.

Feature evidence (audited 2026-04-22 against the PCG Cypher query surface):

- Partial coverage of the Cypher features PCG uses today, including:
  - `MATCH` / `OPTIONAL MATCH`
  - `MERGE` with implicit and explicit `ON CREATE SET` / `ON MATCH SET`
  - Variable-length paths `*1..N`, `*0..N`, unbounded `*`
  - `shortestPath()` with relationship type filters
  - `UNWIND $rows AS row` batched writes
  - `WITH` chaining, `COLLECT(DISTINCT ...)` with map literals
  - `labels()`, `type()`, `nodes()`, `relationships()`, `startNode()`,
    `endNode()`, `length()`
  - `WHERE EXISTS { MATCH ... }` pattern predicates
  - `any(...)`, `all(...)` predicates
  - `CASE WHEN ... THEN ... ELSE`, list comprehensions, `coalesce()`
  - Single-property `CREATE CONSTRAINT ... IS UNIQUE`
  - Composite `CREATE CONSTRAINT ... IS NODE KEY`
  - `CREATE INDEX ... IF NOT EXISTS`
  - Fulltext procedure creation via
    `CALL db.index.fulltext.createNodeIndex(...)`
- Failed PCG-hot-path syntax probes against `/tmp/nornicdb-headless`
  on 2026-04-22:
  - PCG schema uses composite node `IS UNIQUE`, for example
    `REQUIRE (f.name, f.path, f.line_number) IS UNIQUE`; NornicDB
    returned `invalid CREATE CONSTRAINT syntax`.
  - PCG's Neo4j fulltext fallback uses multi-label
    `CREATE FULLTEXT INDEX ... FOR (n:A|B|C) ...`; NornicDB returned
    `invalid CREATE FULLTEXT INDEX syntax`.
  - The same run passed the procedure fallback
    `db.index.fulltext.createNodeIndex(...)` and
    `COLLECT(DISTINCT {map literal})`.
- Workaround probes against the same binary passed:
  - Composite node identity can be expressed as
    `REQUIRE (f.name, f.path, f.line_number) IS NODE KEY`.
  - Multi-label fulltext can be expressed with the procedure form
    `db.index.fulltext.createNodeIndex(...)`.
  - This is an adapter-compatibility option, not a production schema flip:
    Neo4j's key constraints are an Enterprise-only class, while PCG's
    current composite `IS UNIQUE` constraints are the shared production
    schema contract.
- PCG therefore routes graph schema bootstrap through a backend schema
  dialect:
  - `neo4j` receives the shared schema unchanged.
  - `nornicdb` receives composite node identity as `IS NODE KEY` while
    preserving the procedure-based fulltext form.
  - `nornicdb` skips the Neo4j multi-label `CREATE FULLTEXT INDEX` fallback
    because the verified multi-label path is
    `db.index.fulltext.createNodeIndex(...)`.
  - This routing is intentionally restricted to schema DDL; graph writes,
    query handlers, and MCP tools remain behind shared ports and conformance
    gates.
- Bolt 4.x fully implemented, Bolt 5.x backward compatible with negotiation.
- PCG uses `github.com/neo4j/neo4j-go-driver/v5`; wire compatibility expected.
- NornicDB exposes explicit Bolt transaction hooks in the runtime
  `nornicdb serve` path, so PCG can test Neo4j-style grouped canonical writes
  against it. PCG keeps those grouped writes behind
  `PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` until conformance proves
  rollback, timeout, and no-partial-write behavior on the PCG workload.
- The 2026-04-23 grouped-write safety probe against a rebuilt
  linuxdynasty-fork headless binary at `/tmp/nornicdb-headless-pcg-rollback`
  (`v1.0.42-hotfix`) passed the PCG Neo4j-driver path: the PCG canonical
  repository/file/function grouped commit succeeded, grouped rollback marker
  count was `0`, clean explicit rollback marker count was `0`,
  failed-statement explicit rollback marker count was `0`, and the timeout
  probe left no partial write. That makes grouped writes a valid conformance
  surface for the fixed binary; promotion still requires a release-backed
  fixed NornicDB binary plus the broader matrix and perf gates. The promotion
  gate is
  `PCG_NORNICDB_REQUIRE_GROUPED_ROLLBACK=true go test ./cmd/pcg -run TestNornicDBGroupedWriteRollbackConformance`.

Non-standard extras NornicDB provides (not required by PCG today, but
potentially useful later): vector search, hybrid retrieval, tritemporal
facts, as-of reads, graph-ledger modeling, MCP server, GPU acceleration for
semantic workloads.

Performance claims (NornicDB README): 12x-52x LDBC speedups over Neo4j on
published workloads, hybrid retrieval at low single-digit ms locally.
**These numbers are not measured against the PCG workload.** PCG's workload
is heavy on variable-length path traversal, `UNWIND` batched writes from the
reducer, and per-repo scope filtering. LDBC speedups do not translate
automatically; perf claims must be re-measured against PCG queries before
adoption.

## Problem Statement

PCG needs a graph backend that:

- Preserves authoritative graph truth across `local_authoritative`,
  `local_full_stack`, and `production` profiles.
- Is lighter to operate than Neo4j while remaining correct under the
  same query surface.
- Allows laptop-scale authoritative graph queries without requiring
  Compose.
- Does not force us to maintain two divergent graph codepaths
  indefinitely.

## Decision

This ADR is a **provisional** adoption decision. Adoption lands in stages
gated by evidence.

### 1. Adopt NornicDB as candidate backend for `local_authoritative` profile

PCG introduces a new runtime profile, `local_authoritative`, that runs the
lightweight local host plus a user-level NornicDB sidecar. This profile
unlocks the high-authority graph queries that `local_lightweight` refuses.

NornicDB runs as a separate process. Laptop installs default to the
headless `nornicdb-headless` artifact; the full `nornicdb` binary remains
an explicit opt-in for users who accept the larger UI / local-LLM payload.
The current installer slice accepts an explicit source artefact with
`pcg install nornicdb --from <source>` and copies the verified binary to
`${PCG_HOME}/bin/nornicdb-headless`. Supported sources are local binaries,
local tar archives, and URL-backed tar archives; pinned no-arg
download/signature installation remains a promotion prerequisite. The sidecar is inspectable by
`pcg graph status`, `pcg graph logs`, owner-aware `pcg graph stop`, foreground
`pcg graph start`, and stopped-owner `pcg graph upgrade --from <source>` today.
Pinned release selection and signature verification remain future work. Its runtime
lifecycle is tracked in the workspace
data root (`owner.json` records the graph PID, loopback ports, and
per-workspace credentials copied from the graph credential file with `0600`
file permissions).

It does not run embedded in the `pcg` binary. The "lightweight" goal is
preserved by:

- one-command explicit-source install today, pinned no-arg install before promotion
- loopback-only ports owned by the workspace lock
- process ownership tied to the workspace lock
- clean install / uninstall / upgrade

### 2. Evaluate promotion to `local_full_stack` and `production`

If NornicDB passes the full capability-conformance matrix on the
`local_authoritative` profile, it moves into the `local_full_stack`
conformance run. If it passes there, it moves into production evaluation
against real PCG workload shapes.

Promotion is evidence-gated. No profile is upgraded to "supported on
NornicDB" until:

- the capability matrix passes for that profile
- reducer bulk-write throughput meets or exceeds the current Neo4j baseline
  on the PCG workload
- 896-repo scale validation on the remote E2E instance succeeds
- operational burden (backup, recovery, upgrade, migration) is documented

### 3. Dual-backend operation during evaluation

PCG supports both Neo4j and NornicDB adapters simultaneously during the
evaluation window. Operators select the graph backend via the
`PCG_GRAPH_BACKEND` environment variable:

- `PCG_GRAPH_BACKEND=neo4j` — default today, preserves current behavior
- `PCG_GRAPH_BACKEND=nornicdb` — new adapter

This dimension is also surfaced in responses (optional `truth.backend`
field) and in telemetry span / metric labels.

### 4. Plan for Neo4j deprecation

If NornicDB passes all three profile gates, PCG will:

- Announce Neo4j deprecation with a defined support window.
- Ship migration tooling from Neo4j to NornicDB.
- Keep the Neo4j adapter supported through the deprecation window.
- Flip the default `PCG_GRAPH_BACKEND` value to `nornicdb` at the end of
  the window.

Until then, Neo4j remains the default. NornicDB is opt-in.

### 5. Reject outright embedding

NornicDB does not ship as an in-process Go library. This ADR does not
attempt to embed it. The "lightweight" outcome is delivered by:

- one-command laptop install of a verified headless artefact through
  `pcg install nornicdb --from <source>` today, with pinned release
  download and signature verification required before promotion
- sidecar process lifecycle owned by the local host
- loopback-only health and Bolt endpoints recorded in `owner.json`
- deterministic shutdown sequencing documented in
  `local-host-lifecycle.md`

The earlier rejection in ADR 2026-04-20 of "embedded graph as co-equal
local truth path" stands. A sidecar with a strict install + lifecycle
contract is materially different from an in-process embed; this ADR is
explicit about that distinction.

## Rejection Criteria

NornicDB adoption is abandoned if any of the following is observed during
conformance evaluation:

- Critical Cypher feature gap on a PCG hot path that cannot be worked around
  without rewriting multiple handlers (for example, composite unique
  constraints, fulltext index creation, or `COLLECT(DISTINCT {map literal})`
  failing to execute as PCG writes it).
- Reducer bulk-write throughput on PCG workload shapes falls meaningfully
  below the Neo4j baseline with no clear path to close the gap.
- Bolt handshake or driver incompatibility with
  `github.com/neo4j/neo4j-go-driver/v5` that cannot be resolved by driver or
  adapter configuration.
- MVCC / snapshot-isolation overhead measurably harms single-snapshot-per-tx
  projection writes against PCG's reducer acceptance model.
- Multi-label MATCH or the fulltext index syntax PCG uses today does not
  execute cleanly.

If any rejection criterion triggers, the capability-port decomposition still
stands. Any future candidate graph backend is evaluated through the same
matrix.

## Migration Path Summary

1. Land the `local_authoritative` profile: sidecar installer, adapter
   behind `GraphQuery` and `GraphWrite` ports, data-root + lifecycle
   updates, conformance suite run at laptop scale.
2. If the laptop gate passes, run the conformance suite against Compose
   (`local_full_stack`) with NornicDB in place of Neo4j.
3. If the Compose gate passes, run conformance + perf against the remote
   896-repo E2E instance (`production`).
4. On full pass: announce deprecation, ship migration tooling, flip the
   default.

## Consequences

### Positive

- Single authoritative graph backend across laptop, Compose, and production
  if the gates pass.
- Lighter operational surface than Neo4j without reintroducing local graph
  drift.
- Pure Go supply chain.
- Capability-port pattern proven a second time.

### Negative

- Non-trivial evaluation work: adapter implementation, conformance runs at
  three scales, perf comparison.
- Dual-backend operation period adds wiring complexity until deprecation
  closes.
- Version pinning and supply chain for a third-party graph binary becomes a
  first-class concern.

### Operational guardrails

- Default graph backend stays Neo4j until all three profile gates pass.
- `PCG_GRAPH_BACKEND` is validated at startup; no silent default drift.
- Response `truth.backend` field is optional but consistent across CLI /
  HTTP / MCP when surfaced.
- Operator-visible health probe covers both backends when present.

## Validation Requirements

Before the sidecar is called "supported" on `local_authoritative`:

1. `GraphQuery` + `GraphWrite` adapters pass PCG's existing handler tests.
2. Schema dialect verification passes on a real NornicDB instance:
   `TestNornicDBSchemaAdapterVerification` must execute the complete rendered
   NornicDB schema. The exact-Neo4j syntax probe remains useful evidence for
   upstream parser parity, but local support is gated on the rendered adapter
   schema.
3. Compose smoke test indexes a repo end-to-end with NornicDB in place of
   Neo4j.
4. Performance envelope at laptop scale meets the `local_authoritative`
   targets documented in `local-performance-envelope.md`.

Before promotion to `local_full_stack`:

5. Conformance matrix passes for every capability that Neo4j passes today.
6. Reducer bulk-write throughput parity or better.

Before promotion to `production`:

7. 896-repo remote instance parity on query and write paths.
8. Backup / recovery / upgrade story documented.

### Current Syntax Gate Result

`go test ./cmd/pcg -run TestNornicDBSyntaxVerification -count=1 -v`
skips by default unless `PCG_NORNICDB_BINARY` is set. The explicit run below
is intentionally part of the promotion gate, not the default unit-test suite:

```bash
PCG_NORNICDB_BINARY=/tmp/nornicdb-headless \
  go test ./cmd/pcg -run TestNornicDBSyntaxVerification -count=1 -v
```

Result on 2026-04-22: **failed**. Composite node `IS UNIQUE` and
multi-label `CREATE FULLTEXT INDEX` did not parse. The
`db.index.fulltext.createNodeIndex(...)` fallback and
`COLLECT(DISTINCT {map literal})` probes passed. Therefore NornicDB remains
an evaluation candidate only; `local_authoritative` must not be documented
as supported until those syntax gaps are resolved or the PCG schema layer
has a reviewed backend-specific compatibility plan.

`TestNornicDBCompatibilityWorkarounds` passed against the same binary with
composite `IS NODE KEY` and the multi-label fulltext procedure form. That
workaround is viable only behind a graph-backend schema adapter or an upstream
NornicDB parser fix; it must not replace the default Neo4j schema globally.

`TestNornicDBSchemaAdapterVerification` passed against the same binary after
the schema-dialect router rendered NornicDB-compatible DDL. This validates the
adapter approach for bootstrap schema only; broader graph-read and graph-write
conformance still must pass before promotion.

Manual MCP smoke on 2026-04-23 used
`PCG_HOME=/tmp/pcg-local-authoritative-e2e2` and
`PCG_CANONICAL_WRITE_TIMEOUT=2s`. The local host indexed the PCG repo, MCP
`search_file_content` returned matching Go files from `postgres_content_store`,
and MCP `find_code` returned the `startManagedLocalGraph` function with
`truth.profile=local_authoritative` and `truth.basis=content_index`.
The same run intentionally showed canonical graph projection degrading with
`neo4j execute timed out after 2s: context deadline exceeded`, which proves the
local content-search path is isolated from NornicDB graph-write stalls. This
does not promote NornicDB; it only proves the laptop coding workflow remains
usable while the backend remains an evaluation candidate.

Source audit on 2026-04-23 confirmed that NornicDB's actual `nornicdb serve`
Bolt path wires `DBQueryExecutor` with `BeginTransaction`,
`CommitTransaction`, and `RollbackTransaction`; targeted headless/no-local-LLM
NornicDB transaction tests passed with
`go test -tags 'noui nolocalllm' ./pkg/bolt ./pkg/txsession ...`. PCG therefore
added a backend capability router instead of permanently hiding grouped writes.
The stricter PCG sidecar probe uses the exact Neo4j-driver path PCG uses. The
rebuilt linuxdynasty-fork binary at `/tmp/nornicdb-headless-pcg-rollback`
passed that probe after fixing transaction-wrapper reuse for recursive
`UNWIND ... MATCH ... MERGE` execution and database-scoped Bolt rollback.
Normal NornicDB runs stay sequential until that fixed binary is release-backed
and the broader adapter matrix passes, while
`PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` exposes grouped writes for adapter
conformance only.

## Status Summary

This ADR commits PCG to **evaluating** NornicDB as the single graph backend
across all profiles, with Neo4j as the fallback and deprecation target if
evaluation succeeds. The ADR is explicitly provisional; promotion requires
evidence, not advocacy.
