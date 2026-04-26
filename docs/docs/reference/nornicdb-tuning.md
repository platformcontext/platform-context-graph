# NornicDB Tuning Reference

This page is the operator map for PCG's NornicDB-specific environment
variables. Use it when `local_authoritative` indexing is correct but a
repo-scale run exposes a bounded write timeout, slow phase, or compatibility
gate.

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

## Semantic Write Budget

| Variable | Default | Scope | Use |
| --- | --- | --- | --- |
| `PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES` | `Annotation=100,Function=10,ImplBlock=10,Module=10,Variable=10` | reducer semantic entity materialization | Overrides NornicDB row caps for semantic labels after parser-enriched semantic metadata proves expensive. |

Semantic materialization is a reducer-owned phase. Do not copy canonical caps
blindly; semantic labels should be narrowed only after timeout summaries name
the semantic label and row count.

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

Watch future heavy write families such as call edges, infra edges, and other
shared reducer domains. If they need different treatment, add phase metadata
and tuning only after repo-scale evidence proves the existing canonical or
semantic controls do not describe the bottleneck.
