# ADR: NornicDB As Candidate Graph Backend

**Date:** 2026-04-22
**Status:** Accepted with conditions (2026-04-23)
**Authors:** Allen Sanabria
**Deciders:** Platform Engineering

**Acceptance Conditions (must remain true for acceptance to hold):**

- release-backed rollback-safe NornicDB binary published and pinned in
  `go/cmd/pcg/nornicdb_release_manifest.json`
- Chunk 5 backend conformance suite passes against NornicDB for
  `GraphQuery` and `GraphWrite` adapters
- Chunk 5b matrix runs pass against `local_authoritative`,
  `local_full_stack`, and `production` profiles with recorded perf evidence
- signature verification policy defined and enforced for installed binaries
- Neo4j remains the default `PCG_GRAPH_BACKEND` until Chunk 7 deprecation
  criteria are met
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
| Profile/backend admission | In progress | `0e4d8a5f`, current branch local-host profile/backend gating, current branch loopback-TCP sidecar lifecycle and shared Bolt-driver path, manual smoke with `/tmp/nornicdb-headless` showing healthy owner + clean Ctrl-C shutdown; `575ca864` added `TestNornicDBSyntaxVerification` and `TestNornicDBCompatibilityWorkarounds`; `5f5a781e` added schema-dialect routing and `TestNornicDBSchemaAdapterVerification`; current branch managed-install discovery prefers `${PCG_HOME}/bin/nornicdb-headless` after explicit env override; 2026-04-22 temporary-home smoke proved local_authoritative start/status/logs/stop with NornicDB; 2026-04-23 MCP smoke proved content-index-backed `search_file_content` and `find_code` continue to work while canonical graph projection degrades on a bounded NornicDB write timeout; current branch lets `pcg install nornicdb --from <source>` consume local binaries, local tar archives, macOS packages, and URLs; current branch remote installs honor `cmd.Context()` cancellation and use `PCG_NORNICDB_INSTALL_TIMEOUT` (`30s` default) when slower links need a larger budget; 2026-04-23 published fork release `https://github.com/linuxdynasty/NornicDB/releases/tag/v1.0.42-hotfix` with `nornicdb-headless-darwin-arm64.tar.gz` (SHA-256 `61c483c606e039c4be67192252b03420e03cd1985d2005a8ea6614272cbc4af7`), and current branch bare `pcg install nornicdb` now resolves to that rollback-fixed headless asset on covered hosts while bare pinned `--full` remains unavailable until a matching fixed full artefact exists; current branch `TestLocalAuthoritativeStartupEnvelope` measured startup readiness at the owner-record plus ingester handoff with the pinned bare-install binary: cold start `9.045253708s`, warm restart `490.996625ms` | signature policy, broader host coverage, broader query/memory perf |
| Operator CLI surface | In progress | `da35d729`, current branch `pcg graph status`; current branch `pcg install nornicdb [--from <source>] [--sha256 <hex>] [--force] [--full]` installs from the pinned manifest or from a local binary/archive/package/URL, honors `Ctrl-C` on remote downloads, accepts `PCG_NORNICDB_INSTALL_TIMEOUT=<duration>` for slower links, and keeps headless as the bare-install default while only allowing `--full` when the manifest publishes a matching fixed full artifact for the current host; current branch `pcg graph logs`; current branch owner-aware `pcg graph stop`; current branch foreground `pcg graph start`; current branch stopped-owner `pcg graph upgrade --from <source>`; current branch `pcg watch` / `pcg graph start` now render a live local progress panel from the shared status store (owner/profile/backend header, collector/projector/reducer lanes, and queue pressure) instead of a fake percentage bar; 2026-04-22 smoke proved install → start → status running → logs → stop → status stopped | signature verification, broader release coverage |
| Adapter conformance | In progress | current branch routes NornicDB canonical writes through bounded phase-group transactions by default, applies Bolt `tx_timeout` metadata plus client context deadlines, preserves production Neo4j grouped writes, and adds the explicit `PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` conformance switch for proving NornicDB grouped writes; current branch also makes the default NornicDB phase-group window explicit via `PCG_NORNICDB_PHASE_GROUP_STATEMENTS` (`500` by default) so repo-scale dogfood runs can tune the safe path without flipping into grouped conformance mode, now adds `PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS` (`25` by default) to shrink only the canonical `entities` hot spot without lowering every other phase-group batch, now adds `PCG_NORNICDB_ENTITY_BATCH_SIZE` (`100` by default) so only normal entity upsert statements get smaller row batches on NornicDB, now exposes `PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES=Function=15,Struct=50,Variable=10,...` so heavier row families can be capped independently without recompiling, and now also exposes `PCG_NORNICDB_ENTITY_LABEL_PHASE_GROUP_STATEMENTS=Function=5,Struct=15,Variable=5,...` so repo-scale reruns can narrow only the grouped transaction size for the heaviest labels instead of lowering the statement cap for every entity family; 2026-04-23 rebuilt linuxdynasty-fork headless binary `/tmp/nornicdb-headless-pcg-rollback` (`v1.0.42-hotfix`) passed `TestNornicDBGroupedWriteSafetyProbe` and strict `TestNornicDBGroupedWriteRollbackConformance`: PCG repository/file/function grouped commit succeeded, grouped rollback marker count `0`, clean explicit rollback marker count `0`, failed-statement explicit rollback marker count `0`, and timeout probe left no partial write; the same fixed binary is now published as a release-backed headless tarball and pinned in `go/cmd/pcg/nornicdb_release_manifest.json`; current branch now routes call-chain path queries through a backend-aware Cypher builder so NornicDB uses anchored `shortestPath` matches plus raw `nodes(path)` projection while Neo4j keeps the existing projected-node-map shape; current branch also routes transitive callers/callees through backend-aware `/api/v0/code/relationships` traversal builders that resolve the canonical entity first and then traverse by anchored entity id on NornicDB; current branch dead-code keeps the graph-backed candidate scan but intentionally returns derived truth plus structured root-model analysis, including Go exported public-package roots, parser-backed Python FastAPI/Flask/Celery decorator roots, and parser-backed JavaScript/TypeScript Next.js/Express route roots, now routes NornicDB through the explicit `NOT EXISTS { MATCH ... }` candidate-query form documented upstream, and exposes an explicit `limit` plus `truncated` signal instead of silent bounded truncation; direct `UNWIND $rows AS row MERGE ...` canonical-entity probes against the release-backed binary remained query-unsafe in live dogfood, and 2026-04-23 source inspection traced the repo-scale failure to NornicDB's substring-based `isShortestPathQuery` router treating substituted entity values like `TestHandleCallChainReturnsShortestPath` as shortest-path Cypher, so the current branch now keeps batched `UNWIND ... MATCH ... MERGE` entity writes for normal rows but peels `shortestPath` / `allShortestPaths`-bearing rows into singleton parameterized fallback statements instead of abandoning the batched writer entirely; the fresh self-repo rerun then showed `Function` entity rows at `100` were still the remaining timeout shape (`25` grouped statements of `rows=100` hit the full `3m` limit), so the current branch first narrowed `Function`, corrected the local-authoritative child-binary rebuild path so `pcg graph start` actually launched the rebuilt `pcg-ingester`, and then used the new success-log `first_statement` telemetry to confirm repeated `Function rows=25` chunks first land in roughly `18-72s` and then degrade to `105s` by chunk `13/21` while still staying under the old timeout wall, which is what motivated the new per-label statement-cap seam; the next clean rerun with the baked-in defaults showed `Function rows=25` / `10` statements still drifting into the high-30s seconds by the 13-minute mark, so the branch narrowed the built-in Function statement cap to `5`; a direct follow-up rerun proved that statement-cap change alone mostly smoothed chunk latency rather than improving per-statement throughput, and the first narrower row experiment at `Function rows=10` with the same `5`-statement grouped cap dropped the early Function chunks into the roughly `1.5s-1.9s` band but over-fragmented the lane, so the current branch now promotes `Function rows=15` into the built-in default after the next clean rerun proved it reaches `Variable rows=25` with stable early chunks around `19.9s-21.4s`; the same earlier reruns then advanced past Function and exposed the next blocking family directly: `Variable rows=100` at `25` grouped statements timed out at the full `3m`, the first follow-up narrowed that to `rows=50` / `10` grouped statements and bought survival up to roughly `168.7s` before timing out again at the full `3m`, the latest 2026-04-24 rerun still spent roughly `20s-27s` per chunk at `Variable rows=25` / `5` statements, and the current branch now narrows `Variable` again to `rows=10` while keeping the `5`-statement cap for the next clean rerun; the same per-label seams are now applied to `Struct`, and operators can override either row cap or statement cap without another code change; current branch now also groups canonical entity batches by `label + file_path`, matches the file anchor once per statement, and removes `file_path` from every row payload, and the fresh 2026-04-24 rebuilt-binary rerun immediately pushed deep `Function rows=15` chunks into roughly `0.3s-1.9s` instead of the earlier `2s-9s+` band; a second fresh 2026-04-24 overlap-proof rerun then deliberately triggered another repository generation while the first generation was still deep in `Function`, and queue state held at `pending=1, in_flight=1` instead of the old overlapping `in_flight=2` shape | full `GraphQuery`/`GraphWrite` adapter, matrix runs, repo-scale self-repo rerun with the selective singleton fallback plus per-label row and statement caps plus file-scoped entity batching and same-scope projector fencing in place, and the foreground `pcg graph start` dogfood lane still shows a tail `ack projector work: begin: context canceled` after the canonical write completes |
| Performance + promotion gates | In progress | current branch `TestLocalAuthoritativeStartupEnvelope`; 2026-04-23 run with `PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless` measured `local_authoritative` startup readiness at cold start `9.045253708s` and warm restart `490.996625ms`, both under the documented startup envelope; current branch `TestLocalAuthoritativeCallChainSyntheticEnvelope`; 2026-04-23 run with the same binary measured synthetic call-chain p95 `789.709µs` through the real `local_authoritative` `/api/v0/code/call-chain` handler after the backend-routed NornicDB query rewrite; current branch `TestLocalAuthoritativeTransitiveCallersSyntheticEnvelope`; 2026-04-23 run with the same binary measured synthetic transitive-caller p95 `1.917916ms` through the real `local_authoritative` `/api/v0/code/relationships` handler; current branch `TestLocalAuthoritativeDeadCodeSyntheticEnvelope`; 2026-04-23 run with the same binary measured synthetic dead-code p95 `3.174125ms` through the real `local_authoritative` `/api/v0/code/dead-code` handler after the staged NornicDB-friendly synthetic seed and explicit `NOT EXISTS { MATCH ... }` candidate-query routing; current branch `./scripts/verify_graph_analysis_compose.sh` now adds the required fresh Compose full-stack conformance proof for direct callers, transitive callers, shortest call-chain path, dead-code results, and canonical Neo4j `CALLS` edges over the dedicated `tests/fixtures/graph_analysis_compose` corpus; 2026-04-23 self-repo NornicDB dogfood showed the repo-scale canonical write remains the gating perf problem rather than the read/query contract: sequential mode with `PCG_CANONICAL_WRITE_TIMEOUT=120s` kept the generation in flight for minutes, grouped conformance mode failed cleanly after `125.119083917s` with `canonical atomic write: neo4j execute group timed out after 2m0s`, and current branch projector lease heartbeats now prove the long-running source-local claim itself stays alive past the old 5-minute expiry (`attempt_count=1`, status `running`, renewed `claim_until`) instead of being reclaimed into duplicate projector attempts; 2026-04-23 direct `UNWIND $rows AS row MERGE ...` probes against the release-backed binary were still query-unsafe, so the current branch records the safer bounded-phase-group tuning path and leaves the canonical writer on the proven per-entity semantics; fresh 2026-04-24 self-repo reruns then showed repeated `Function rows=25` grouped chunks still degrading from roughly `18-72s` up to `105s` by chunk `13/21`, which is why the branch first added per-label grouped statement caps before the next full rerun; the next clean rerun then advanced through Function and Struct but still failed at `Variable rows=100` with `25` grouped statements after the full `3m` timeout; the follow-up rerun with the baked-in defaults showed `Function rows=25` / `10` statements still drifting into the high-30s seconds by the 13-minute mark before Variable was reached, so the branch narrowed Function’s grouped statement cap to `5`; the direct row-width experiments that followed then showed the real throughput lever: keeping the same `5`-statement grouped cap but reducing `Function` rows to `10` dropped the first Function chunks into roughly the `1.5s-1.9s` band, but that lane over-fragmented and stayed stuck in Function too long, while the next clean rerun with `Function rows=15` reached `Variable rows=25` and kept the first Variable chunks stable around `19.9s-21.4s`, which is why the current branch now promotes `Function rows=15` into the built-in default before the next clean run; the earlier `Variable rows=50` / `10` rerun already proved that family survives much longer, but still drifts from about `94s` through `168.7s` and eventually times out at the full `3m`, which is why the branch keeps Variable on `rows=25` / `5` for the next clean run | reducer-throughput perf smoke, idle/active memory budgets, production-scale comparison, repo-scale proof for the new phase-group default, entity-containment optimization beyond the current grouped-by-file rewrite, foreground `graph start` ack-cancel tail |

Latest 2026-04-25 NornicDB dogfood evidence:
- `Function=15` is the better built-in compromise: it avoids the over-fragmented `Function=10` lane and still reaches `Variable` with stable early chunks around `19.9s-21.4s`
- the next repo-scale blocker is now `retract`, not `entities`; bundling all 9 stale-delete statements into one grouped transaction overflowed NornicDB's request budget
- the branch now executes NornicDB retract statements sequentially and sanitizes backend error text before projector dead-letter persistence so NUL bytes cannot break Postgres updates
- the current branch now goes one step further than the earlier `label + file_path` grouping: canonical entity node upserts are split from file containment edges, node upserts batch across files with the simple NornicDB-friendly `UNWIND ... MERGE (n:<Label> {uid: row.entity_id}) SET n += row.props` shape, and `phase=entity_containment` attaches those nodes back to files in a separately measured batch phase
- projector same-scope claim fencing is now proven too: a deliberate second-generation trigger during the first generation's `Function` phase held queue state at `pending=1, in_flight=1` instead of the old overlapping `in_flight=2` failure mode
- the latest clean rerun finally exposed the next real bottleneck directly: `Variable rows=25` still spends roughly `20s-27s` per 5-statement chunk, so the built-in Variable row cap now narrows to `10` while leaving the grouped-statement cap at `5`
- the follow-up `Variable rows=15` / `5`-statement experiment improved individual Variable chunks into roughly the `11.6s-17.4s` band, but it still took about `23m` to reach Variable and ran about `35m` total before manual stop, so it is not the next default candidate
- after re-reading NornicDB's performance and migration docs, the branch identified a local-host startup gap: `pcg graph start` applied Postgres schema but skipped graph schema bootstrap, leaving NornicDB without the schema-backed `MERGE` lookup preconditions its hot-path cookbook documents
- current branch now applies the backend-routed graph schema immediately after NornicDB sidecar readiness and before owner-record publication or reducer/ingester startup, using the same NornicDB schema dialect as `bootstrap-data-plane`
- the branch now emits rolling and final `nornicdb entity label summary` logs with `phase`, per-label rows, statements, executions, grouped chunks, total duration, max execution duration, and row-width totals so the next tuning slice can compare node-upsert cost against containment-edge cost before changing more defaults
- the first remote self-repo rerun after the entity/containment split exposed a schema-dialect correctness issue rather than a timeout: translating composite `IS UNIQUE` to `IS NODE KEY` made sparse `Annotation` rows fail on required `name`; the follow-up run also proved the current NornicDB binary still rejects PCG composite `IS UNIQUE`, so current branch skips unsupported composite uniqueness DDL for NornicDB and relies on separate `uid` uniqueness constraints for canonical merge identity
- the same remote run proved canonical entity node upsert is no longer the main bottleneck: `phase=entities` completed in `25.523448885s` total, including `Function` at `3.10382615s` and `Variable` at `20.695746985s`; `phase=entity_containment` is now dominant, with `Function` containment alone taking `248.58715967s`
- current branch now keeps the split node-upsert / containment-edge shape only for backends that support node-only batched `MERGE`, and routes the pinned NornicDB release through the proven file-scoped combined shape: match the `File` anchor with `$file_path`, unwind entity rows for that file, upsert nodes, and attach `CONTAINS` in one statement. The opt-in syntax gate records why this is necessary: the current release-backed NornicDB binary collapses the standalone node-only batch shape, while the combined shape preserves row-bound entity identity. The NornicDB branch in `/Users/allen/os-repos/NornicDB-pcg-map-merge-hotpath` now proves the faster MERGE-first row-file shape needs `SET += row.props` support inside the generalized `UNWIND/MERGE` batch hot path and unique-constraint-backed `MERGE` lookups for `File.path` and canonical `uid`; PCG exposes `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true` only as a patched-binary evaluation switch until those fixes are release-backed and pinned.
- remote self-repo dogfood confirms the tuning target: map-merge alone reduced statement fragmentation but still let `MERGE` chunk time grow with graph size; adding unique-constraint lookup cut `Function` from `40.039s` to `12.589s` at 750 rows and from `158.568s` to `46.566s` at roughly 2.1k rows, while the `files` phase dropped from roughly `26s-28s` to `7.351s`.
- the follow-up evidence is intentionally not a new PCG tuning claim yet: `Function` completed at `9021` rows in `444.997825518s`, `Struct` completed at `916` rows in `81.059759011s`, and `Variable` was still progressing past `5000` rows in `563.749941325s`. That leaves a linear write-path cost that needs NornicDB CPU/heap profiling before we decide whether the next fix belongs in Badger/index maintenance, Cypher hot-path execution, Bolt transaction handling, or PCG statement shape.
- after the NornicDB unique-constraint validation patch (`023ec51`) rebuilt on the 16-vCPU remote test host, canonical source-local projection stopped being the bottleneck: `Variable` completed all `40163` rows in `30.375581617s`, the full canonical `entities` phase completed in `42.085095138s`, and source-local projection succeeded with `55295` facts in `49.603476029s`. The same run proves `.git` was not being parsed (`dirs_skipped..git=1`). The next failure moved to reducer `semantic_entity_materialization`, where PCG was still forcing NornicDB through the older scalar compatibility writer and hit the `15s` bounded write timeout.
- current branch now routes NornicDB semantic entity materialization back through the batched `UNWIND $rows AS row` writer because the patched NornicDB binary now supports the required row-based write shape. This keeps the compatibility decision at the adapter seam: when NornicDB lacks a generally useful primitive, patch NornicDB; when the primitive exists, PCG should use the shared batched path instead of preserving stale defensive routing.
- the first rerun with the batched semantic writer still timed out after `18.140664853s`; the new timeout summary narrowed the failing statement to only `Annotation rows=19`, so the remaining reducer issue is the semantic per-field `SET` / `coalesce` Cypher shape rather than row width. Current branch now routes NornicDB semantic writes through `UNWIND ... MERGE ... SET n += row.properties`, keeps `PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES=Function=15,Variable=10,...` for high-cardinality labels, and includes semantic label/row count in timeout errors so future failures are diagnosable without another blind rerun.
- upstream status as of 2026-04-25: the unique-constraint validation fix (`https://github.com/orneryd/NornicDB/pull/115`), the `UNWIND ... MATCH ... MERGE ... SET n += row.props ... MERGE relationship` hot-path/router fix (`https://github.com/orneryd/NornicDB/pull/116`), and unique-constraint-backed `MERGE` lookup (`https://github.com/orneryd/NornicDB/pull/118`) are merged into NornicDB `main`. PCG should rebuild the next dogfood binary from upstream `main`, keep using explicit `--from`/`PCG_NORNICDB_BINARY` until an upstream release asset is published and pinned, and then rerun the self-repo dogfood lane against the release-backed headless asset before removing temporary fork-binary language from the promotion gate.
- 2026-04-25 follow-up upstream handoff completed with `#118`, which teaches NornicDB `MERGE` lookup to use single-property unique-constraint metadata instead of falling back to label scans. Copilot review comments on PRs `#116` and `#118` were addressed before merge: `#116` counts only rows that survive required `MATCH` lookups and falls back safely for unsupported `OPTIONAL MATCH` mutation shapes; `#118` treats non-comparable unique lookup values as lookup misses instead of panicking.
- the 16-vCPU remote self-repo dogfood run against the stacked `#115 + #116 + #118` headless binary completed cleanly: owner start `2026-04-25T02:32:17Z`, empty queue at `2026-04-25T02:37:14Z`, source-local projection succeeded with `55384` facts in `50.461321256s`, canonical `entities` completed in `42.723968989s`, `Function` stayed flat through `9045` rows with about `2.857s` total label time, `semantic_entity_materialization` succeeded in `142.392295866s`, and `.git` remained skipped by the collector.
- the follow-up run rebuilt directly from upstream `main` at merge commit `501a121d7882cadf2bb3ec657178a54b33d5967b` (`NornicDB v1.0.42-hotfix`) and reproduced the same result without the temporary integration branch: owner start `2026-04-25T04:13:44Z`, healthy at `2026-04-25T04:18:20Z`, collector emitted `55409` facts while skipping `.git`, source-local projected `55384` facts, canonical `Function` wrote `9045` rows in `2.836596812s`, `semantic_entity_materialization` succeeded in `141.031360077s`, `sql_relationship_materialization` succeeded in `217.718543222s` for `291` edges, and a clean `pcg graph stop` left no owner or graph sidecar running.
- that same completed run moves the next bottleneck to SQL relationship writes rather than canonical entities: `sql_relationship_materialization` wrote only `291` edges but took `222.19561979s` while the NornicDB process consumed multiple CPU cores. The next compatibility slice should profile and narrow the `UNWIND ... MATCH (source:SqlTable|SqlView|...) ... MERGE relationship` shape before changing more PCG batch defaults; likely candidates are multi-label indexed `MATCH` planning or a backend-dialect split into single-label relationship statements.
- source inspection of NornicDB `main` narrowed the SQL relationship bottleneck to a missing database hot path rather than a PCG batch-size problem: `UNWIND ... MATCH ... MATCH ... MERGE (source)-[rel:TYPE]->(target) SET rel.*` fell back to per-row generic execution because the `UnwindMergeChainBatch` parser did not accept lookup-first mutation chains, `|` label alternatives, relationship variables, or relationship property `SET`. The local branch `/Users/allen/os-repos/NornicDB-pcg-sql-edge-hotpath` adds that support in commit `05f4b3c` plus `TestUnwindMatchRelationshipSetBatch_PCGSQLRelationshipShape`; focused tests and headless build pass.
- remote self-repo dogfood against that patched `v1.0.43` headless binary validated the performance claim: total owner start to healthy dropped to about `3m06s`, `sql_relationship_materialization` dropped from `217.718543222s` to `3.921462s`, source-local projection completed in `34.279920s`, and the remaining bottleneck is now `semantic_entity_materialization` at `131.247187s`. The owner stopped cleanly afterward with no graph sidecar left running.
- `https://github.com/orneryd/NornicDB/pull/119` now carries the SQL relationship hot-path fix upstream. With SQL edges no longer dominant, the next evidence pass inspected the completed graph snapshot and found semantic materialization rewrote `7,622` `Function` nodes even though only about `2,475` carried additional callable semantic metadata such as `docstring`, `class_context`, `impl_context`, decorators, type parameters, or async/annotation context. The current PCG branch therefore tightens Go semantic extraction and projector triggering so plain Go functions remain canonical-only while enriched Go callables still publish semantic readiness. This is a correctness-preserving write-set reduction, not another NornicDB batch-size workaround.
- the first remote rerun with that write-set reduction exposed the next semantic label boundary: `Module rows=45` exceeded the bounded `15s` semantic write timeout. The branch now caps NornicDB semantic `Module` rows at `10` by default, keeping the fix scoped to the newly measured label family instead of lowering the whole semantic writer.
- the `Module=10` rerun proved that cap moved the boundary forward and then exposed `ImplBlock rows=103` as the next timeout family after `52.188006393s`. The branch now also caps NornicDB semantic `ImplBlock` rows at `10`, preserving the evidence-driven per-label approach instead of globally shrinking the semantic writer.
- the `ImplBlock=10` rerun completed successfully on the same remote host and PR `#119` binary: source-local projected `55,439` facts in `34.065189964s`, SQL relationships stayed fixed at `2.587845711s`, semantic materialization succeeded in `127.982626601s`, code-call projection completed after semantic readiness in `4.282710051s`, and total owner start-to-healthy stayed about `3m06s`. This proves the cap removes the timeout but not the semantic wall; the next adapter evidence must profile or attribute semantic label cost before another PCG-side tuning change.
- the branch now adds NornicDB-only semantic statement attribution in the reducer execute-only path so the next run records `graph_backend`, semantic label, row count, duration, and statement summary for every semantic statement. This is an observability slice only: it does not change semantic write ordering, timeout behavior, or grouped rollback conformance.
- the temporary dogfood-only local NornicDB integration branch is no longer needed for these three fixes. Build the next evaluation binary directly from latest upstream `main` with `go build -tags 'noui nolocalllm' ...`, use it only through explicit `PCG_NORNICDB_BINARY` or installer `--from` inputs until a release-backed asset is pinned, and keep any future NornicDB fix as a clean focused branch off upstream `main`.

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
  - PCG's Neo4j-compatible composite
    `CREATE CONSTRAINT ... REQUIRE (...) IS UNIQUE` form returned
    `invalid CREATE CONSTRAINT syntax`.
  - PCG's Neo4j fulltext fallback uses multi-label
    `CREATE FULLTEXT INDEX ... FOR (n:A|B|C) ...`; NornicDB returned
    `invalid CREATE FULLTEXT INDEX syntax`.
  - The same run passed the procedure fallback
    `db.index.fulltext.createNodeIndex(...)` and
    `COLLECT(DISTINCT {map literal})`.
- Workaround probes against the same binary passed:
  - Composite node identity can also be expressed as
    `REQUIRE (f.name, f.path, f.line_number) IS NODE KEY`, but PCG does not
    use that form for sparse semantic labels because node keys make every
    participating property mandatory.
  - Multi-label fulltext can be expressed with the procedure form
    `db.index.fulltext.createNodeIndex(...)`.
  - This is an adapter-compatibility option, not a production schema flip:
    Neo4j's key constraints are an Enterprise-only class, while PCG's
    current composite `IS UNIQUE` constraints are the shared production
    schema contract.
- PCG therefore routes graph schema bootstrap through a backend schema
  dialect:
  - `neo4j` receives the shared schema unchanged.
  - `nornicdb` skips unsupported composite `IS UNIQUE` DDL. PCG does not
    translate those constraints to `IS NODE KEY` because node keys require
    every participating property while sparse semantic labels such as
    `Annotation` may not have all properties present.
  - `nornicdb` keeps the single-property `uid` uniqueness constraints that
    canonical writes use as merge identity and preserves the procedure-based
    fulltext form.
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
The current installer slice accepts either a pinned bare install or an explicit
source artefact with `pcg install nornicdb [--from <source>]` and copies the
verified binary to `${PCG_HOME}/bin/nornicdb-headless`. Supported explicit
sources are local binaries, local tar archives, macOS packages, and matching
URLs. The pinned bare install only resolves host platforms that have real
published assets in the embedded release manifest; today that means upstream
the rollback-fixed `linuxdynasty/NornicDB` macOS arm64 headless tarball.
Signature verification and broader
coverage remain promotion prerequisites. The sidecar is inspectable by
`pcg graph status`, `pcg graph logs`, owner-aware `pcg graph stop`, foreground
`pcg graph start`, and stopped-owner `pcg graph upgrade --from <source>` today.
Its runtime lifecycle is tracked in the workspace
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

Startup perf smoke on 2026-04-23 used the pinned bare-install binary at
`/tmp/pcg-bare-install-smoke/bin/nornicdb-headless`:

```bash
PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless \
PCG_LOCAL_AUTHORITATIVE_PERF=true \
  go test ./cmd/pcg -run TestLocalAuthoritativeStartupEnvelope -count=1 -v
```

That run measured readiness at the owner-record plus ingester handoff with:

- cold start: `9.045253708s`
- warm restart: `490.996625ms`

This proves the current `local_authoritative` startup path meets the documented
startup envelope. It does not yet prove the broader laptop perf contract:
query latency, dead-code scan time, reducer throughput, and memory budgets
remain promotion gates.

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

## NornicDB Compatibility Workflow (MANDATORY)

When PCG hits a NornicDB incompatibility (Cypher parse rejection, rollback
misbehavior, driver shape mismatch, missing procedure, etc.), the PCG contributor
MUST follow this workflow before writing a PCG-side workaround:

1. **Search the NornicDB source first.** The upstream NornicDB repository is
   checked out locally at:

   - `/Users/allen/os-repos/NornicDB/` — upstream reference
   - `/Users/allen/os-repos/NornicDB-pcg-bolt-rollback/` — PCG-maintained fork
     for the grouped-write rollback conformance work

   Use `rg` or the Grep tool against those paths to confirm what the runtime
   actually supports, parses, or rejects. Read the source of truth before
   inferring behavior from test failures.

2. **Decide the patch surface.** Every NornicDB incompatibility resolves to
   exactly one of:

   - **NornicDB supports it already** (parser difference, missing workaround
     in PCG). Fix: adjust PCG's Cypher, driver call, or adapter to match
     what NornicDB's source-of-truth code accepts.
   - **NornicDB has a documented workaround** (procedure form, alternate
     syntax, different rollback API). Fix: route PCG through the supported
     form behind the backend-dialect seam (`schemaDialect`,
     `canonicalExecutorForGraphBackend`, `buildCallChainCypher`, etc.). Do
     not branch query handlers on backend brand.
   - **NornicDB must be patched.** The PCG path is correct and NornicDB is
     wrong. Open a branch in `NornicDB-pcg-bolt-rollback`, reproduce with a
     minimal test that mirrors the PCG workload, land the fix, and pin the
     rebuilt binary through the installer's pinned manifest or explicit
     `--from` path until upstream absorbs the change.

3. **Record the decision.** Add the incompatibility, workaround route, and
   upstream patch status to:

   - this ADR's Feature evidence section (for adapter conformance claims)
   - the active Chunk 3.5 or Chunk 4 evidence row in
     `docs/docs/adrs/2026-04-20-embedded-local-backends-implementation-plan.md`
   - the 2026-04-23 grouped-write rollback fork precedent is the template:
     minimal repro in PCG → minimal fix in NornicDB fork → rebuilt binary
     passes `TestNornicDBGroupedWriteRollbackConformance`.

4. **Prefer narrow seams.** Backend-dialect translation belongs in already
   narrow seams (schema DDL, canonical-write executor, call-chain/transitive
   Cypher builders). Do not widen handler, reducer, or MCP tool code with
   `if backend == nornicdb` branches. If a new seam is required, document
   it here before merging.

This workflow protects the capability-port boundary while giving contributors
a clear path to either ship a dialect rendering or patch upstream.

## Status Summary

This ADR is **Accepted with conditions** (2026-04-23). PCG commits to treating
NornicDB as the evaluation graph backend across all profiles, with Neo4j as
the default and deprecation target once every acceptance condition at the top
of this ADR holds. Acceptance is revocable: if any condition regresses
(rollback gate fails, signature policy slips, Chunk 5/5b matrix fails),
acceptance reverts to Proposed and PCG keeps the Neo4j default.
