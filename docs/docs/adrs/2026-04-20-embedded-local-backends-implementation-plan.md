# Implementation Plan: Local Code Intelligence Host, Authoritative Graph Mode, And Backend Conformance

**Date:** 2026-04-20
**Owner:** Allen Sanabria
**Tracks ADR:** `2026-04-20-embedded-local-backends-desktop-mode.md`
**Status:** In Progress (Chunks 1-3 shipped, Chunk 3.5 in progress)

**Companion Specs:**

- `docs/docs/reference/capability-conformance-spec.md`
- `docs/docs/reference/truth-label-protocol.md`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/dead-code-reachability-spec.md`
- `docs/docs/reference/fact-schema-versioning.md`
- `docs/docs/reference/plugin-trust-model.md`
- `docs/docs/reference/local-performance-envelope.md`
- `docs/docs/reference/local-host-lifecycle.md`

---

## Chunk Status

This table reflects the current branch state, including active working-tree
slices in the current PR. It MUST be updated in the same PR that changes
chunk-visible code. Drift between this table, the working tree, and
verification evidence = reviewer rejects PR.

| Chunk | Title | Status | Evidence | Remaining |
| --- | --- | --- | --- | --- |
| 1 | Capability contract + truth labels | Shipped | `488ff808`, `35a3a091` | — |
| 2 | Capability ports (`GraphQuery`, `ContentStore`) | Shipped | `08795558`, `07619013`, `085c91a3` | — |
| 3 | Lightweight local host | Shipped | `a3e05ecf`, `c832a84c`, current branch local-host supervisor + embedded Postgres lifecycle, current branch `TestLocalAuthoritativeStartupEnvelope` with 2026-04-23 cold start `9.045253708s` and warm restart `490.996625ms` evidence attached in docs | — |
| 3.5 | NornicDB laptop sidecar + `local_authoritative` profile | In progress | `0e4d8a5f`, current branch profile/backend and runtime-gating slices, `da35d729`, current branch authoritative sidecar lifecycle + shared Bolt-driver path + graph-aware reclaim, manual smoke with `/tmp/nornicdb-headless` showing healthy owner + clean Ctrl-C shutdown, current branch binary verification + random workspace credentials, `575ca864` opt-in syntax/workaround gates, `5f5a781e` schema-dialect router + `TestNornicDBSchemaAdapterVerification` pass, current branch `pcg install nornicdb [--from <source>] [--full]` installer with managed `${PCG_HOME}/bin/nornicdb-headless` discovery from the pinned manifest or from local binaries, local archives, macOS packages, and URLs, current branch remote install downloads honor `cmd.Context()` cancellation and use `PCG_NORNICDB_INSTALL_TIMEOUT` (`30s` default) when slower links need a larger budget, current branch bare install now pins the rollback-fixed `linuxdynasty/NornicDB` `v1.0.42-hotfix` headless tarball on covered hosts; bare pinned `--full` remains intentionally unavailable until a matching fixed full artefact exists, current branch `pcg graph logs` workspace log reader, current branch owner-aware `pcg graph stop`, current branch foreground `pcg graph start` local-host shortcut, current branch stopped-owner `pcg graph upgrade --from <source>`, 2026-04-22 smoke with temporary `PCG_HOME=/tmp/pcg-local-authoritative-smoke` proving install → start → status running → logs → stop → status stopped, 2026-04-23 smoke with `PCG_HOME=/tmp/pcg-local-authoritative-e2e2` proving MCP `search_file_content` and `find_code` return real repo results from the content index while NornicDB canonical graph projection times out and reports degraded status, 2026-04-23 published fork release `https://github.com/linuxdynasty/NornicDB/releases/tag/v1.0.42-hotfix` with `nornicdb-headless-darwin-arm64.tar.gz` (SHA-256 `61c483c606e039c4be67192252b03420e03cd1985d2005a8ea6614272cbc4af7`) and repointed the embedded installer manifest to it, current branch NornicDB grouped-write capability router with `PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` reserved for conformance, 2026-04-23 rebuilt linuxdynasty-fork headless binary `/tmp/nornicdb-headless-pcg-rollback` (`v1.0.42-hotfix`) passed `TestNornicDBGroupedWriteSafetyProbe` and strict `TestNornicDBGroupedWriteRollbackConformance` with grouped/clean-explicit/failed-explicit rollback marker count `0` and no timeout partial write, current branch `TestLocalAuthoritativeStartupEnvelope`; 2026-04-23 run with `PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless` measured cold start `9.045253708s` and warm restart `490.996625ms` at the owner-record plus ingester handoff; 2026-04-23 self-repo dogfood with current branch binaries and owner-record wired API proved `pcg list`, `pcg find name handleRelationships`, and `pcg analyze dead-code --repo platform-context-graph-local-codeintel` work through a live NornicDB-backed local host once `NEO4J_DATABASE=nornic` is supplied to the API; current branch projector lease heartbeats now renew long-running source-local claims, and a fresh 2026-04-23 self-repo `PCG_HOME=/tmp/pcg-nornic-heartbeat-fixed.*` dogfood run proved the original projector work item stayed on `attempt_count=1`, advanced from `claimed` to `running`, and extended `claim_until` past the old 5-minute expiry instead of being reclaimed into a duplicate attempt; current branch keeps the safe per-entity canonical writer path but now phase-groups default NornicDB canonical writes into bounded `PCG_NORNICDB_PHASE_GROUP_STATEMENTS` transactions (`500` by default), because a direct `UNWIND $rows AS row MERGE ...` probe against the release-backed binary remained query-unsafe even though the grouped rollback path itself passed conformance; 2026-04-23 source inspection and self-repo dogfood then isolated the remaining repo-scale entity failure to NornicDB's substring-based `isShortestPathQuery` router when substituted row values contain names like `TestHandleCallChainReturnsShortestPath`, and current branch now caps the canonical `entities` phase independently with `PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS` (`25` by default) so repo-scale authoritative runs can shrink only the entity hot spot without collapsing every other phase-group batch; current branch now splits those `shortestPath` / `allShortestPaths` rows into singleton parameterized fallback statements while preserving batched entity writes for normal rows, adds `PCG_NORNICDB_ENTITY_BATCH_SIZE` (`100` by default) so NornicDB can shrink only the per-statement row batch for normal entity upserts without forcing the same row count onto other canonical phases, exposes `PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES=Function=15,Struct=50,Variable=25,...` so operators can tune heavy row families without recompiling, and now also exposes `PCG_NORNICDB_ENTITY_LABEL_PHASE_GROUP_STATEMENTS=Function=5,Struct=15,Variable=5,...` so repo-scale reruns can shrink only the grouped transaction size for the heaviest entity labels instead of lowering the statement cap for the entire entity phase; after correcting the local-authoritative child-binary rebuild path so `pcg graph start` actually launched the new `pcg-ingester`, fresh 2026-04-24 reruns proved the new success-log `first_statement` telemetry is enough to follow repo-scale progress live, with repeated `Function rows=25` chunks first landing in roughly `18-72s` and then degrading to `105s` by chunk `13/21` while still staying under the old `3m` timeout wall, which is what motivated the new per-label statement-cap seam; the next clean rerun with the baked-in defaults showed `Function rows=25` / `10` statements still drifting into the high-30s seconds by the 13-minute mark, so the branch narrowed the built-in Function statement cap to `5`; a direct follow-up rerun proved that statement-cap change alone mostly smoothed chunk latency rather than improving per-statement throughput, and the first narrower row experiment at `Function rows=10` with the same `5`-statement grouped cap dropped the early Function chunks into the roughly `1.5s-1.9s` band but over-fragmented the lane, so the current branch now promotes `Function rows=15` into the built-in default after the next clean rerun proved it reaches `Variable rows=25` with stable early chunks around `19.9s-21.4s`; the same earlier reruns then advanced past Function and exposed the next blocking family directly: `Variable rows=100` at `25` grouped statements timed out at the full `3m`, the first follow-up narrowed that to `rows=50` / `10` grouped statements and bought survival up to roughly `168.7s` before timing out again at the full `3m`, and the current branch now narrows `Variable` again to `rows=25` / `5` statements by default for the next clean rerun; current branch now also groups canonical entity batches by `label + file_path`, matches the file anchor once per statement, and keeps `file_path` out of every row payload; the fresh 2026-04-24 self-repo rerun with rebuilt binaries and a clean `PCG_HOME` immediately showed the effect on the hottest surviving family: `Function` grouped chunks now land in roughly `0.3s-1.9s` even for full `rows=15` batches instead of the earlier multi-second drift; current branch `pcg watch` / `pcg graph start` now render a live local progress panel from the shared status store (owner/profile/backend header, collector/projector/reducer lanes, and queue pressure) instead of a fake percentage bar; a second fresh 2026-04-24 overlap-proof rerun then deliberately triggered another repository generation while the first generation was still deep in `Function`, and queue state held at `pending=1, in_flight=1` instead of the old overlapping `in_flight=2` shape | signature policy, broader host coverage, broader query/memory perf envelope, repo-scale self-repo rerun with the selective singleton fallback plus per-label row and statement caps plus file-scoped entity batching and same-scope projector fencing in place, and the foreground `pcg graph start` dogfood run still needs a clean finish without the `ack projector work: begin: context canceled` tail |
| 4 | Authoritative graph analysis hardening | In progress | current branch backend-routed call-chain Cypher builder keeps Neo4j on the existing projected-node-map `shortestPath` query while routing NornicDB through anchored `shortestPath` matches plus raw `nodes(path)` normalization in Go; current branch transitive callers/callees route through `/api/v0/code/relationships` with backend-aware traversal builders, `analyze callers|calls --transitive --depth`, and MCP `find_all_callers` / `find_all_callees`; current branch dead-code now runs as a dedicated query module that keeps the graph-backed candidate scan but defaults to derived truth, excludes Go entrypoints, direct Go Cobra/stdlib-HTTP/controller-runtime signature roots, parser-backed Python FastAPI/Flask/Celery decorator roots, parser-backed JavaScript/TypeScript Next.js route exports and Express handler registrations, Go exported public-package symbols, test files, and obvious generated code, strips comments before query-time source heuristics run, prefers parser-emitted `dead_code_root_kinds` from entity metadata when that content metadata exists, now also emits parser-backed Go Cobra `Run` / `RunE` registrations, direct/proven `ServeMux` HTTP registrations, Python FastAPI/Flask/Celery decorator roots, and JavaScript/TypeScript Next.js/Express route roots as derived framework roots, preserves `dead_code_root_kinds` across the mixed native+SCIP supplement merge path, requires pointer-form `*http.Request` for stdlib HTTP handler roots, dedupes merged controller-runtime aliases across import paths, hardens the Express detector seam with `javaScriptExpressServerSymbols(...)` so the dead-code registration path explicitly requires a typed `server_symbols []string` contract, emits structured `analysis` metadata about the currently modeled root categories plus `modeled_framework_roots`, `roots_skipped_missing_source`, and parser-vs-fallback framework-root counters, and exposes a bounded `limit` plus `truncated` signal instead of silently truncating at 100 rows; current branch dead-code also routes NornicDB through the explicit `NOT EXISTS { MATCH ... }` candidate-query form and proves the live `local_authoritative` handler path with `TestLocalAuthoritativeDeadCodeSyntheticEnvelope` after switching the synthetic seed to a staged NornicDB-friendly containment write flow; current branch `pcg analyze dead-code` accepts `--repo` selectors that resolve repository name, slug, local path, or canonical ID through `/api/v0/repositories` before posting the canonical `repo_id`; current branch code-query HTTP handlers also resolve repository selectors in `repo_id` fields through the repository catalog so code search, relationships, dead-code, call-chain, and complexity requests can use canonical IDs, names, repo slugs, or indexed paths at the public boundary; current branch repository context, story, stats, and coverage routes now resolve the `{repo_id}` path segment through the same exact-match repository selector seam, so repository MCP/API users can address those routes by canonical ID, name, repo slug, or indexed path while the server still normalizes to canonical repo IDs before graph/content reads, and the escaped-path regression tests now prove `%2F` selectors survive real `http.ServeMux` route decoding; current branch content file/entity reads, content search, and `entities/resolve` now also normalize repository selectors in `repo_id` and `repo_ids`, so MCP/API callers can scope those requests by canonical ID, name, repo slug, or indexed path without changing the underlying canonical query semantics; current branch CLI `pcg stats [repo-or-path]` now preserves repository selectors such as repo names and slugs while still canonicalizing a real existing local path to an absolute path before calling `/api/v0/repositories/{repo_id}/stats`; current branch content-store repository selector resolution now uses exact `ingestion_scopes` matches instead of relisting the full repository catalog on every code-query request, which removes the hot-path full scan without adding cache staleness; current branch now annotates Go selector calls with receiver metadata and upgrades calls on the enclosing method receiver to exact class-context resolution, which restores same-file edges like `handleRelationships -> transitiveRelationshipsGraphRow` without loosening import-qualified calls such as `fmt.Println`; current branch `TestJavaScriptExpressServerSymbols`, `TestDefaultEngineParsePathGoEmitsDeadCodeRootKinds`, `TestDefaultEngineParsePathGoDoesNotMarkValueRequestAsHTTPHandlerRoot`, `TestDefaultEngineParsePathGoEmitsDeadCodeRegistrationRoots`, `TestDefaultEngineParsePathGoIgnoresUnknownHandleFuncReceivers`, `TestDefaultEngineParsePathGoAnnotatesReceiverSelectorCalls`, `TestDefaultEngineParsePathPythonEmitsDeadCodeRootKinds`, `TestDefaultEngineParsePathPythonDoesNotMarkUnknownDecoratorsAsDeadCodeRoots`, `TestDefaultEngineParsePathJavaScriptEmitsDeadCodeRootKinds`, `TestMergeSCIPSupplementPreservesDeadCodeRootKinds`, `TestHandleCallChainRewritesShortestPathAnchorsForNornicDB`, `TestHandleCallChainSupportsEntityIDAndRepoScopedLookupForNornicDB`, `TestHandleRelationshipsReturnsTransitiveCallers`, `TestHandleRelationshipsReturnsTransitiveCallersForNornicDB`, `TestHandleDeadCodeReturnsDerivedTruthAndAnalysisMetadata`, `TestHandleDeadCodeExcludesDefaultEntrypointsTestsAndGeneratedCode`, `TestHandleDeadCodeExcludesGoPublicAPIRootsOutsideInternalPackages`, `TestHandleDeadCodeExcludesGoFrameworkRootsBySignature`, `TestHandleDeadCodeExcludesPythonFrameworkRootsFromMetadata`, `TestHandleDeadCodeExcludesJavaScriptFrameworkRootsFromMetadata`, `TestHandleDeadCodeUsesParserRootMetadataWithoutSourceCache`, `TestHandleDeadCodeUsesParserRegistrationRootMetadataWithoutSourceCache`, `TestHandleDeadCodeDoesNotTreatGoCommentSubstringsAsFrameworkRoots`, `TestHandleDeadCodeReportsModeledGoFrameworkRootsInAnalysis`, `TestHandleDeadCodeReportsMissingSourceForGoFrameworkRootChecks`, `TestHandleDeadCodeRespectsLimitAndReportsTruncation`, `TestRunAnalyzeDeadCodeResolvesRepoSelectorAlias`, `TestRunAnalyzeDeadCodeFailsOnAmbiguousRepoSelector`, `TestHandleDeadCodeResolvesRepositorySelectorAlias`, `TestHandleCallChainResolvesRepositorySelectorAlias`, `TestContentReaderMatchRepositoriesReturnsExactMatches`, `TestContentReaderResolveRepositoryRejectsAmbiguousMatches`, `TestGetRepositoryContextAcceptsRepositorySlugSelector`, `TestGetRepositoryContextDecodesEscapedRepositorySlugPathValue`, `TestGetRepositoryStoryAcceptsRepositoryPathSelector`, `TestGetRepositoryStatsAcceptsRepositorySlugSelector`, `TestContentHandlerReadFileResolvesRepositorySelectorAlias`, `TestContentHandlerSearchFilesResolvesRepositorySelectorAliases`, `TestContentHandlerSearchEntitiesResolvesRepositorySelectorAlias`, `TestResolveEntityAcceptsRepositorySelectorAlias`, `TestRunStatsPreservesRepositorySelector`, `TestRunStatsCanonicalizesExistingPathSelector`, `TestExtractCodeCallRowsResolvesGoReceiverVariableCallsWithoutTreatingImportsAsLocal`, and 2026-04-23 `TestLocalAuthoritativeCallChainSyntheticEnvelope` / `TestLocalAuthoritativeTransitiveCallersSyntheticEnvelope` / `TestLocalAuthoritativeDeadCodeSyntheticEnvelope` with synthetic call-chain p95 `789.709µs`, synthetic transitive-caller p95 `1.917916ms`, and synthetic dead-code p95 `3.174125ms` through the real `local_authoritative` handlers; current branch also adds `./scripts/verify_graph_analysis_compose.sh`, a dedicated full-stack compose gate over `tests/fixtures/graph_analysis_compose` that proves direct callers, transitive callers, shortest call-chain path, dead-code results, and the expected canonical `CALLS` edges after a fresh bootstrap run, plus `./scripts/verify_graph_analysis_dogfood_compose.sh`, a self-repo dogfood lane that discovered the receiver-call gap and now validates it against `platform-context-graph-local-codeintel`; local Compose now bounds Neo4j to `512m` heap and `512m` page cache by default through `PCG_NEO4J_HEAP_INITIAL_SIZE`, `PCG_NEO4J_HEAP_MAX_SIZE`, and `PCG_NEO4J_PAGECACHE_SIZE` so single-repo dogfood verification does not rely on unbounded JVM defaults; 2026-04-23 live self-repo NornicDB dogfood proved the current branch can already serve `pcg list`, `pcg find name handleRelationships`, and `pcg analyze dead-code --repo platform-context-graph-local-codeintel`, but graph-backed CLI queries remain blocked by repo-scale canonical projection timing out before the canonical nodes become queryable | broader framework/public-API/reflection root registry beyond current direct Go, Python decorator, and JavaScript/TypeScript route rules, remove legacy query-time string matching after a guaranteed reindex window, active-repo perf evidence including parser-overhead measurement, keep the new dogfood compose lane green under restart/degraded-stack conditions, repo-scale canonical-write tuning or redesign for NornicDB, consider lightweight caching only if exact-match selector queries still show measurable pressure |
| 5 | Backend conformance suite | Not started | — | all |
| 5b | NornicDB conformance across profiles | Not started | — | matrix run vs `local_authoritative`, `local_full_stack`, `production`; PCG-workload perf comparison vs Neo4j baseline |
| 6 | OCI collector plugin contract | Not started | — | all |
| 7 | Neo4j deprecation path (contingent on 5b pass) | Not started | — | dual-backend operation docs, migration tooling Neo4j → NornicDB, deprecation window + default flip |

Chunk 4 query-truth addendum: the older table-row wording that graph-backed
CLI queries were blocked by canonical projection is superseded by the
2026-04-25 live NornicDB dogfood proof below. The current branch now proves
direct `CALLS`, transitive caller, entity-ID call-chain, and entity-resolution
repo identity API queries for `handleRelationships -> transitiveRelationshipsGraphRow`
through the live local-authoritative API.

Latest 2026-04-26 NornicDB dogfood evidence:
- the narrower `Function=10` lane lowered per-statement cost but over-fragmented the self-repo run, so the built-in row cap now moves to `Function=15`
- that `Function=15` rerun advanced through `Variable` with stable early chunks around `19.9s-21.4s`
- the next repo-scale blocker is now the `retract` phase, not `entities`, so the branch runs NornicDB retract statements sequentially instead of bundling all stale deletes into one grouped transaction
- projector dead-letter persistence now sanitizes backend error text before writing to Postgres so NUL bytes from NornicDB cannot break failure updates
- the latest rerun proved `Variable rows=25` is still too wide after the earlier fixes, spending roughly `20s-27s` per 5-statement chunk, so the built-in Variable row cap now narrows to `10` while leaving the grouped-statement cap at `5`
- the current branch now supersedes the earlier `label + file_path` grouping with a cleaner split: canonical entity node upserts batch across files with the simple NornicDB-friendly `UNWIND ... MERGE (n:<Label> {uid: row.entity_id}) SET n += row.props` shape, while `phase=entity_containment` attaches those nodes back to files in a separately measured batch phase
- projector same-scope claim fencing is now proven too: a deliberate second-generation trigger during the first generation's `Function` phase held queue state at `pending=1, in_flight=1` instead of the old overlapping `in_flight=2` failure mode
- the follow-up `Variable rows=15` / `5`-statement experiment improved individual Variable chunks into roughly the `11.6s-17.4s` band, but it still took about `23m` to reach Variable and ran about `35m` total before manual stop, so it is not the next default candidate
- after re-reading NornicDB's performance and Neo4j migration docs, the branch identified a more fundamental local-only gap: `pcg graph start` applied Postgres schema but did not apply the NornicDB graph schema before starting reducer/ingester, which meant schema-backed `MERGE` hot paths could fall back to label scans even though PCG's checked-in schema defines the right `uid` constraints
- current branch now applies the backend-routed graph schema immediately after NornicDB sidecar readiness and before owner-record publication or child startup, preserving the same NornicDB schema dialect used by `bootstrap-data-plane`
- the branch now emits rolling and final `nornicdb entity label summary` logs with `phase`, per-label rows, statements, executions, grouped chunks, total duration, max execution duration, and row-width totals so the next tuning slice can optimize cumulative node-upsert and containment-edge cost instead of reacting to isolated chunk logs
- the first remote self-repo rerun after the entity/containment split failed fast on `Annotation` because the old NornicDB schema dialect translated composite `IS UNIQUE` to `IS NODE KEY`, which incorrectly required sparse semantic labels to carry `name`; the follow-up run also proved the current NornicDB binary still rejects PCG composite `IS UNIQUE`, so current branch now skips unsupported composite uniqueness DDL for NornicDB and keeps `uid` uniqueness as the canonical merge identity
- the same remote run proved the split changed the real bottleneck: `phase=entities` completed in `25.523448885s` total, including `Function` at `3.10382615s` and `Variable` at `20.695746985s`; the remaining slow lane is now `phase=entity_containment`, where `Function` containment alone took `248.58715967s`, so the next tuning slice must target containment-edge shape rather than node upsert row width
- current branch now keeps the split node-upsert / containment-edge shape for backends that support node-only batched `MERGE`, but routes the pinned NornicDB release through the proven file-scoped combined shape: each statement matches the `File` anchor with `$file_path`, unwinds entity rows for that file, upserts nodes, and attaches `CONTAINS` in the same statement. The opt-in syntax gate caught that the current release-backed NornicDB binary collapses the standalone node-only batch shape, while the combined shape preserves row-bound entity identity. The NornicDB hot-path branch in `/Users/allen/os-repos/NornicDB-pcg-map-merge-hotpath` now proves the desired faster shape needs row-safe `SET += row.props` support inside the generalized `UNWIND/MERGE` batch path plus unique-constraint-backed `MERGE` lookup for `File.path` and canonical `uid` constraints; PCG therefore keeps `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true` as an explicit patched-binary evaluation switch until those NornicDB fixes are released and pinned.
- entity resolution now treats NornicDB optional-projection placeholders such as `r.id` / `r.name` as missing repo identity and hydrates code entities from the content store plus repository catalog before graph-only workload backfill, preventing `pcg find name` from returning projection strings as canonical repo truth.
- remote self-repo dogfood on the patched NornicDB branch shows the root cause clearly: before unique-constraint lookup, `Function` took `40.039s` for 750 rows and `158.568s` for roughly 2,142 rows while chunk duration climbed toward `8s`; after unique-constraint lookup, the same lane took `12.589s` for 750 rows and `46.566s` for roughly 2,110 rows, and the `files` phase dropped from roughly `26s-28s` to `7.351s`. That confirms the major remaining cost was NornicDB label-scan fallback on schema-constrained `MERGE`, not `.git` parsing, Postgres, or machine starvation.
- the same `dogfood-mapmerge-unique-*` run later completed `Function` at `9021` rows in `444.997825518s` and `Struct` at `916` rows in `81.059759011s`; `Variable` remained active past `5000` rows in `563.749941325s` with chunk times drifting into the `6.5s-6.6s` range. The queue stayed single-owner (`in_flight=1`, no overdue claims), so the next optimization must profile NornicDB's remaining linear write path rather than guessing at more PCG batch defaults.
- after the NornicDB unique-constraint validation patch (`023ec51`) rebuilt on the 16-vCPU remote test host, the same self-repo dogfood run proved the root cause was fixed for canonical writes: `Variable` completed all `40163` rows in `30.375581617s`, the full canonical `entities` phase completed in `42.085095138s`, source-local projection succeeded with `55295` facts in `49.603476029s`, and the collector log explicitly skipped `.git` (`dirs_skipped..git=1`). The next blocker moved out of canonical projection and into reducer `semantic_entity_materialization`, which still used the old scalar NornicDB compatibility writer and timed out after `15s`.
- upstream handoff is now split into two clean NornicDB PRs instead of one local fork patch stack: `https://github.com/orneryd/NornicDB/pull/115` carries the indexed UNIQUE validation fix that made canonical projection finish in roughly `49.6s`, and `https://github.com/orneryd/NornicDB/pull/116` carries the `UNWIND ... MATCH ... MERGE ... SET n += row.props ... MERGE relationship` hot-path/router fix needed by the row-property semantic writer. Chunk 3.5 remains in patched-binary evaluation until those PRs are merged, released, and pinned in PCG's installer manifest.
- current branch now routes NornicDB semantic entity materialization through the same batched `UNWIND $rows AS row` writer used by Neo4j because the patched NornicDB binary now supports the needed `UNWIND` / schema-backed `MERGE` / row property update shape. This is an adapter-routing cleanup after the upstream-style database fix, not another batch-size workaround.
- the first rerun with that batched semantic writer still timed out after `18.140664853s`; the new diagnostic then narrowed the failing statement to only `Annotation rows=19`, proving the issue was the semantic per-field `SET n.foo = row.foo` / `coalesce(...)` shape rather than row count. Current branch now routes NornicDB semantic writes through the same row-properties shape that canonical projection proved (`UNWIND ... MERGE ... SET n += row.properties`) and keeps `PCG_NORNICDB_SEMANTIC_ENTITY_LABEL_BATCH_SIZES=Function=15,Variable=10,...` for the genuinely high-cardinality semantic labels.
- upstream handoff is now complete: PRs `#115`, `#116`, and `#118` are merged into NornicDB `main`, including unique-constraint validation, the `UNWIND ... MATCH ... MERGE ... SET n += row.props ... MERGE relationship` hot path, and unique-constraint-backed `MERGE` lookup. Copilot review comments were resolved before merge: row counts now reflect required `MATCH` filtering, unsupported `OPTIONAL MATCH` mutations no longer fall through to the read-only UNWIND path, and non-comparable unique lookup values become safe misses instead of panics.
- the 2026-04-25 remote self-repo dogfood run against the stacked `#115 + #116 + #118` binary completed: source-local projection succeeded with `55384` facts in `50.461321256s`, canonical `entities` finished in `42.723968989s`, `Function` stayed flat through `9045` rows with about `2.857s` total label time, `semantic_entity_materialization` succeeded in `142.392295866s`, `sql_relationship_materialization` succeeded in `222.19561979s` for `291` edges, and the queue reached empty about `4m57s` after owner start.
- a follow-up 2026-04-25 remote self-repo dogfood run rebuilt the headless binary directly from upstream NornicDB `main` at merge commit `501a121d7882cadf2bb3ec657178a54b33d5967b` (`NornicDB v1.0.42-hotfix`) with `go build -buildvcs=false -tags 'noui nolocalllm'`. The run reached healthy state about `4m36s` after owner start: source-local emitted `55409` facts and projected `55384` in the same ~`50s` band, canonical `entities` stayed fixed (`Function` `9045` rows in `2.836596812s`; `Struct` `917` rows in `0.361973072s`), `semantic_entity_materialization` succeeded in `141.031360077s`, `sql_relationship_materialization` succeeded in `217.718543222s` for `291` edges, and `pcg graph stop` left `owner_present=false` / `graph_running=false`.
- this changes the next Chunk 3.5 closeout target: canonical entities are no longer the wall on the remote host, while SQL relationship materialization is now disproportionately slow and CPU-bound inside NornicDB. The next slice should inspect the `UNWIND ... MATCH (source:SqlTable|SqlView|...) ... MERGE relationship` path and decide whether to patch NornicDB's multi-label indexed `MATCH` planner or route PCG through a documented single-label backend dialect seam.
- that inspection found the SQL-edge statement was falling out of NornicDB's `UnwindMergeChainBatch` because the post-`UNWIND` mutation starts with lookup `MATCH` clauses, uses `|` label alternatives, binds the relationship variable (`[rel:REFERENCES_TABLE]`), and then sets relationship properties. The local NornicDB worktree `/Users/allen/os-repos/NornicDB-pcg-sql-edge-hotpath` now carries focused fix commit `05f4b3c` and regression tests for the exact PCG SQL relationship shape; `go test -tags 'noui nolocalllm' ./pkg/cypher ./pkg/storage ./pkg/bolt -count=1` and a headless build both pass.
- remote patched-binary dogfood with `/home/ubuntu/os-repos/NornicDB/bin/nornicdb-headless-pcg-sql-edge-hotpath` (`NornicDB v1.0.43`) proved the fix moves the wall again: owner start `2026-04-25T04:40:25Z`, healthy `2026-04-25T04:43:31Z` (~`3m06s`), source-local projection `34.279920s`, `sql_relationship_materialization` `3.921462s` for the same repo, and `semantic_entity_materialization` remains the dominant domain at `131.247187s`; clean stop left `owner_present=false` and `graph_running=false`.
- `https://github.com/orneryd/NornicDB/pull/119` is now open for the SQL-edge hot path. The next PCG-side evidence pass found the semantic domain is spending most of its remaining time re-upserting ordinary Go functions that canonical projection already wrote: the completed snapshot had `7,622` semantic `Function` nodes, but only about `2,475` carried extra callable semantic metadata. The current branch now narrows Go semantic extraction and semantic-intent creation to enriched Go callables, leaving plain Go functions on the canonical-only path while preserving semantic readiness for real semantic follow-ups.
- the first remote rerun with that Go write-set reduction correctly removed the `Function` wall but exposed the next semantic label directly: `Module rows=45` exceeded the bounded `15s` semantic write timeout. The branch now caps NornicDB semantic `Module` rows at `10` by default, matching the same evidence-driven per-label strategy used for `Function` and `Variable`.
- the `Module=10` rerun then progressed to the next measured semantic family and timed out on `ImplBlock rows=103` after `52.188006393s`. The branch now caps NornicDB semantic `ImplBlock` rows at `10` as well; this keeps the default tuned to observed wide-label families while preserving larger batches for labels that have not shown timeout behavior.
- the `ImplBlock=10` rerun completed cleanly against the same PR `#119` NornicDB binary: owner start `2026-04-25T05:21:23Z`, healthy at `2026-04-25T05:24:29Z` (~`3m06s`), source-local projection `34.065189964s` for `55,439` facts, canonical `entities` `26.240370051s`, `sql_relationship_materialization` `2.587845711s`, `semantic_entity_materialization` `127.982626601s`, and code-call projection completed after semantic readiness in `4.282710051s`. Clean stop left `owner_present=false` / `graph_running=false`.
- the first semantic-attribution rerun exposed a NornicDB concurrency bug rather than a PCG timeout: the sidecar panicked with `fatal error: concurrent map read and map write` in `StorageExecutor.findMergeNodeInCache` because cloned executors shared `nodeLookupCache` but each clone copied its own value mutex. PR `#119` branch commit `4521bcb` now shares the cache lock across clones; the regression test failed before the fix, passes after it, `go test -race -tags 'noui nolocalllm' ./pkg/cypher -run TestCloneWithStorageSharesNodeLookupCacheLock -count=1` passes, and the remote branch rebuilt the headless binary successfully.
- the follow-up remote dogfood with that NornicDB lock fix and PCG semantic statement attribution completed cleanly: owner start `2026-04-25T05:46:36Z`, healthy progress `2026-04-25T05:49:42Z` (~`3m06s`), source-local projection `34.099439413s` for `55,471` facts, canonical `entities` `26.301571598s`, `sql_relationship_materialization` `2.546008605s`, `semantic_entity_materialization` `128.151959988s`, and code-call projection completed in `4.456774766s`. The semantic attribution shows the remaining wall is concentrated in a few labels rather than broad graph-write slowness: `ImplBlock` `103` rows across `11` statements took `79.586s`, `Module` `45` rows across `5` statements took `34.734s`, `Protocol` `9` rows took `6.918s`, while `Function` `2,485` rows across `166` statements took only `1.625s`.
- inspection of PCG's Go-owned graph schema then found the exact asymmetry behind that attribution: `Function` and `Variable` had single-property `uid` uniqueness constraints, but the slow module-like semantic labels did not. The current branch now adds `uid` uniqueness constraints for `Module`, `ImplBlock`, `Protocol`, and `ProtocolImplementation` while preserving the separate `Module.name` index used by canonical import-graph writes, and keeps the projector `entityTypeLabelMap` aligned with every schema label that has a `uid` uniqueness constraint. `TestSchemaStatementsContainsUIDConstraints` was tightened from substring matching to exact statement matching after it falsely passed `module_uid_unique` via `terraform_module_uid_unique`, and `TestEnsureSchemaWithBackendExecutesNornicDBStatements` now proves the NornicDB schema bootstrap executes those constraints.
- the clean remote rerun with those schema constraints proved the hypothesis and removed the semantic wall: owner start `2026-04-25T06:03:46Z`, healthy progress `2026-04-25T06:04:49Z` (~`63s`), source-local projection `34.216079101s` for `55,470` facts, `sql_relationship_materialization` `2.583036883s`, `semantic_entity_materialization` `4.827652236s`, and code-call projection `4.265383252s`. The previously slow labels collapsed onto the unique-lookup path: `Module` `45` rows took `0.034952s` total, `ImplBlock` `103` rows took `0.072267s`, `Protocol` `9` rows took `0.004776s`, and `ProtocolImplementation` `3` rows took `0.002808s`. `.git` remained skipped and clean stop left `owner_present=false` / `graph_running=false`.
- PR `#119` review follow-up commit `5121f55` now resolves Copilot's remaining SQL-edge comments before upstream merge: any-label schema misses fall back to label scans for unindexed alternatives, the redundant `AllNodes` fallback is gone, no-op relationship `MERGE` skips mutation notifications, and `CreateEdge` `ErrAlreadyExists` either refetches a concurrent relationship or retries with a new edge id. The NornicDB branch passes `go test -tags 'noui nolocalllm' ./pkg/storage ./pkg/cypher -count=1`.
- PR `#119` follow-up commit `26b901f` resolves the last Copilot thread by making the unindexed `SqlFunction.uid` fallback coverage explicit. Until PR `#119` merges and a release asset is pinned, PCG dogfood and `local_authoritative` validation should use the `pcg-sql-edge-hotpath` branch binary explicitly through `PCG_NORNICDB_BINARY` / installer `--from`.
- the remote self-repo rerun against that exact `#119` binary and PCG commit `5db74ae5` kept the ~one-minute dogfood envelope: owner start `2026-04-25T10:37:11Z`, code-call projection cycle completed `2026-04-25T10:38:20Z` (~`69s`), source-local projection `34.120669469s`, canonical phase-group write `27.299008161s`, `sql_relationship_materialization` `2.629018298s`, `semantic_entity_materialization` `4.870551017s`, and code-call projection `4.302299486s`. The collector skipped `.git` (`dirs_skipped..git=1`), and clean stop left `owner_present=false` / `graph_running=false`.
- the follow-up warm API query proof found a Chunk 4 query-truth issue: `pcg list` and `pcg find name handleRelationships` succeeded against the same NornicDB-backed dogfood graph, but `pcg analyze dead-code --repo platform-context-graph --limit 5` returned IaC/provenance entities such as `ArgoCDApplication`, `KustomizeOverlay`, `HelmValues`, and `K8sResource`. Current branch now gates the graph-backed dead-code candidate query to code labels (`Function`, `Class`, `Struct`, `Interface`) before `LIMIT` and keeps a defensive output guard so stale/non-code backend rows cannot leak into the public result; rebuilding only `pcg-api` on the remote owner and rerunning `pcg analyze dead-code --repo platform-context-graph --limit 5` / `--limit 50` then returned no IaC/provenance results through the live NornicDB-backed API. The same path now fetches a bounded raw-candidate policy buffer (`max(501, 10x + 1)`, capped at `1000`) before applying entrypoint/test/generated/public-API filters so early excluded roots do not make the public result underfill when displayable candidates exist later in the ordered scan; a second remote API rebuild proved `--limit 5` now returns five code entities (`Function`, `Interface`, `Struct`) instead of the previous empty/truncated shape.
- the same live graph then exposed a NornicDB read-dialect issue in code relationships and call-chain: the canonical `CALLS` edge `handleRelationships -> transitiveRelationshipsGraphRow` existed, but the Neo4j-shaped relationship query used `collect(DISTINCT {map})` projections that could leak placeholder property strings, and the Neo4j-shaped call-chain query used parameterized `shortestPath` endpoint anchors that returned no path or hung. Current branch keeps this inside the query adapter seam: NornicDB direct relationship reads now use anchored row queries, transitive callers/callees use bounded one-hop BFS, placeholder relationship properties are stripped, and NornicDB call-chain uses the same bounded BFS rows while Neo4j keeps `shortestPath`. Remote API proof against the same self-repo owner now returns `pcg analyze calls handleRelationships --repo platform-context-graph` with `transitiveRelationshipsGraphRow`, `/api/v0/code/relationships` returns `handleRelationships` as a depth-1 incoming transitive caller, and `/api/v0/code/call-chain` returns the two-node entity-ID chain at depth 1.
- repo-scoped call-chain endpoint names now use graph reachability as a narrow ambiguity tie-breaker: if content finds multiple exact endpoint candidates but exactly one start/end pair is reachable within the requested depth, the API resolves to those entity IDs; otherwise ambiguity remains explicit and actionable.
- a fresh 2026-04-25 remote dogfood rerun on `PCG_HOME=/tmp/pcg-dogfood-fresh.JcCtVs` confirmed the clean-home authoritative lane stays in the fast envelope after the retract/containment fixes: owner start `2026-04-25T17:49:35Z`, `Health: healthy` at `2026-04-25T17:50:41Z` (~`66s`), empty queue at the same checkpoint, `sql_relationship_materialization` `2.709911757s`, `semantic_entity_materialization` `5.067362874s`, and code-call projection cycle completion `4.396658558s` about `72s` after owner start.
- follow-up commit `297da4ca` closes the remaining NornicDB direct-relationship identity gap that dogfood exposed: direct code-relationship metadata and one-hop reads now bridge `id`/`uid` instead of matching `uid` only, and the response path hydrates repo identity before returning results. Live API proof on the same owner now returns canonical `repo_id=repository:r_7dcdc31d` / `repo_name=platform-context-graph` for `pcg find name handleRelationships` and no longer leaks placeholder `repo.id` / `repo.name` values through `pcg analyze calls`.
- follow-up commits `2fd6972c`, `7da2cf13`, and `87de590a` finish that direct-relationship read path: the NornicDB adapter now avoids the broad `id OR uid` predicate, uses ordered indexed `uid` then `id` metadata and one-hop lookups, and emits one-hop relationships as a single relationship-pattern `MATCH` so `type(rel)` survives response filtering. The remote API rebuilt on the same owner with `PCG_GRAPH_BACKEND=nornicdb` now returns direct `CALLS` edges for `pcg analyze calls handleRelationships --repo platform-context-graph` instead of an empty `outgoing` array.
- the next remote owner restart reached canonical retraction and failed on the broad stale `File` delete (`DETACH DELETE f`) because it attempted to remove every previous-generation file and edge in one NornicDB request. Current branch now excludes current materialization file paths from file retraction, so stable files are updated in place during the file upsert phase and only removed or renamed paths are candidates for deletion. The follow-up retract redesign now preserves current directory paths and family-scoped entity IDs as well, expands canonical retract coverage for all projectable labels, and explicitly refreshes touched structural edges before stale entity pruning and upsert so the old wipe/rewrite behavior does not leave stale relationships behind when nodes are preserved. The structural-edge refresh now batches file paths and entity IDs after the next remote rerun proved a single file/entity edge refresh over the full repo path list still exceeded the bounded NornicDB request budget.
- fresh remote dogfood on commit `a083cf92` with `PCG_HOME=/tmp/pcg-dogfood-a083b.IPluPl` proved the scoped retract/file-edge pruning path on a clean graph: owner start `2026-04-25T18:40:56Z`, healthy at `2026-04-25T18:42:01Z` (~65s), collector skipped `.git` (`dirs_skipped..git=1`), snapshot emitted `1,616` files / `56,067` facts in `13.938566986s`, canonical phase-group write completed `9,020` statements in `31.554647267s`, `code_call_materialization` succeeded in `2.015869566s`, `sql_relationship_materialization` in `2.684154892s`, and `semantic_entity_materialization` in `4.97578507s`. The queue drained to `pending=0 in_flight=0 failed=0 dead_letter=0`; live API checks against the fresh NornicDB owner passed `pcg list`, `pcg find name handleRelationships`, `pcg analyze calls handleRelationships --repo platform-context-graph`, `pcg analyze chain handleRelationships transitiveRelationshipsGraphRow --repo platform-context-graph --depth 3`, and `pcg analyze dead-code --repo platform-context-graph --limit 5`; `pcg graph stop` left `owner_present=false` / `graph_running=false`.
- the first remote multi-repo run against `/home/ubuntu/pcg-test-repos` intentionally moved beyond the single self-repo dogfood lane. It discovered the expected repo-directory corpus and skipped `.git` in indexed repos, but dead-lettered `helm-charts` after a `K8sResource` canonical entity chunk of `25` file-scoped one-row inline-containment statements hit the `15s` NornicDB timeout. The failure narrows the next slice: add `K8sResource=5` to the NornicDB entity label phase-group defaults and rerun the same corpus cleanly before judging broader multi-repo performance.
- the follow-up multi-repo rerun with `K8sResource=5` got past the `helm-charts` timeout and shifted the wall to first-generation `retract` work for the two PHP repos. Because those scopes had no prior generation, stale-generation cleanup was a no-op semantically but still expensive operationally. Current branch now propagates `ingestion_scopes.active_generation_id` plus a previous-generation-exists flag through projector claims, marks first-generation canonical materializations, skips stale retract phases only when no prior generation exists, and keeps scoped retraction unchanged for refresh projections or follow-up generations after a failed first attempt.
- the next clean multi-repo rerun proved that grouped-statement caps and row caps are distinct controls. The safe first-generation retract skip moved `portal-php-yc-soldboats` through canonical projection quickly (`entities` completed in `42.280045651s`, `Variable` wrote `19,995` rows in `39.958509486s`), but `helm-charts` still dead-lettered because one `redirects-httproute.yaml` statement carried `29` same-file `K8sResource` rows and hit the `15s` NornicDB timeout. Current branch now adds a NornicDB-only `K8sResource=5` entity row cap as well as the existing `K8sResource=5` grouped-statement cap, so file-scoped inline containment splits large manifests into multiple bounded statements.
- the follow-up multi-repo rerun with the `K8sResource` row cap moved the `helm-charts` scope through canonical projection instead of timing out: `K8sResource` completed `275` rows across `193` statements in `131.135765046s` with `max_statement_rows=5` and max grouped execution `11.914367608s`, under the `15s` deadline. The next blocker shifted to the huge PHP API repo (`216,610` facts), where the generic `files` phase grouped `15` 500-row file-upsert statements and hit the same `15s` deadline. Follow-up commit `1e127fb5` tagged file statements as `phase=files`, emitted file-row summaries, and added a NornicDB-only `PCG_NORNICDB_FILE_PHASE_GROUP_STATEMENTS` cap (`5` default). The next clean rerun proved that grouped-statement cap but still dead-lettered the PHP repo on chunk `2/3` with `5` file statements whose first statement carried `rows=500`; the cap narrowed transaction width but not per-statement row width. Current branch therefore adds `PCG_NORNICDB_FILE_BATCH_SIZE` (`100` default) and a file-only writer row cap so large file inventories can reduce rows inside each file-upsert statement without changing Neo4j defaults or lowering entity/repository/directory phases.
- remote multi-repo validation of commit `13a5b76b` on `/home/ubuntu/pcg-test-repos` proved the file row cap clears the remaining hard blocker: the large PHP API repo's `files` phase completed `71` file statements in `105.489761166s`, with chunks bounded to `rows=100` instead of the previous `rows=500` timeout shape. The same run completed the full local-authoritative queue with `Health: healthy`, projector `succeeded=23 dead_letter=0 failed=0`, reducer `succeeded=169 dead_letter=0 failed=0`, and queue `pending=0 in_flight=0`. The largest remaining cost is now throughput, not correctness: the PHP repo's `Variable` label wrote `174,411` rows across `20,894` statements in `125.913498259s`, and the full canonical write completed in `241.859647305s` without timeout.
- the corrected 2026-04-25 timing harness added live-owner API proof and separated self-repo, focused-regression, and full-corpus evidence. The self-repo run converged in `85s` and passed repository listing, symbol find, direct calls, call-chain, and dead-code CLI checks; the focused `crossplane-xrd-irsa-role` run converged in `20s` with `K8sResource=1`, proving the previous K8sResource timeout was grouped transaction width. The first full `/home/ubuntu/pcg-e2e-full` run advanced to `321/896` repositories in `722s` before dead-lettering on the reducer semantic retract shape, not parsing or `.git` traversal. A follow-up label-scoped retract run avoided the hard timeout but showed first-generation repos still paying no-op semantic cleanup per label. Current branch now promotes `K8sResource=1` to the default grouped cap, skips semantic retract on first-generation first attempts, and keeps NornicDB refresh/retry semantic retract label-scoped so the next full-corpus run measures the next real bottleneck.
- the next full-corpus run got past that first-generation semantic cleanup and found the next real bottleneck: same-scope reducer graph-write contention. `/home/ubuntu/pcg-e2e-full` failed at `722s` on `hapi-amqp` when `semantic_entity_materialization` timed out on `Function rows=4` while `inheritance_materialization` for the same `scope_id` was concurrently writing the graph for about `16s`. Current branch now applies the same ownership principle used for projector work to reducer claims: claim selection rejects scopes with another unexpired claimed/running reducer item, and batch claims choose only one pending/retrying item per scope so unrelated repos keep parallelism without overlapping graph writes for the same repo.
- the reducer-fenced rerun proved that fix and moved the full-corpus wall forward: `hapi-amqp` crossed cleanly with inheritance at `17.615437958s` followed by semantic materialization at `0.026024905s`, then `/home/ubuntu/pcg-e2e-full` failed later at `932s` after `365/896` repos on a source-local `K8sResource rows=5` inline-containment statement in `iac-eks-argocd/teams/devops-team/rbac.yaml`. Current branch now narrows the NornicDB `K8sResource` row cap to `1` and makes graph write timeout errors include the tuning env var (`PCG_CANONICAL_WRITE_TIMEOUT`) so future production-style failures are diagnosable from the error string.
- a follow-up diagnostic run with `PCG_CANONICAL_WRITE_TIMEOUT=30s` moved the full-corpus wall to `1694s` and proved the timeout knob is effective, but it exposed the next real write shape instead of finishing: `semantic_entity_materialization` timed out on `Annotation rows=500`. That slice added a NornicDB semantic `Annotation` row cap so huge annotation batches split before they monopolize the graph writer.
- the rerun with `Annotation=100` moved past that timeout and hit a different concurrency surface: NornicDB returned `conflict: edge ... changed after transaction start` during `inheritance_materialization`. Current branch now treats that optimistic write conflict as transient in the shared graph retry executor and marks exhausted retries queue-retryable, preserving cross-scope parallelism while letting conflict-heavy reducers retry instead of dead-lettering.
- the retry-enabled rerun proved the conflict classifier live, then failed later at `2170s` on a semantic `Function rows=15` statement reaching the `30s` write budget. Current branch narrows NornicDB semantic `Function` rows to `10` while leaving canonical Function tuning unchanged.
- the next full-corpus timing pass used the narrowed Function cap and failed later at `1859s` on `Annotation rows=100` reaching the same `30s` budget, so the branch narrowed Annotation to `50`. The follow-up crossed that wall and reached `504/896` projector scopes before `Annotation rows=50` failed at `1849s`; several successful 50-row Annotation writes were already within roughly five seconds of the deadline. A follow-up with `Annotation=25` crossed the previous `504`-scope wall but still failed on `Annotation rows=25`, with another 25-row statement completing at `25.49501893s`. Current branch narrows only the NornicDB semantic `Annotation` cap to `10` and keeps the timeout as an explicit operator knob rather than raising it again.
- the `Annotation=10` full-corpus timing pass advanced to `1975s` and `522/896` projector scopes before another `Annotation rows=10` timeout. The attribution profile showed the bigger active bottleneck was not another semantic cap: `fsbo-mobile/.yarn/releases/yarn-4.13.0.cjs` generated `45,381` facts from `59` files and repeatedly consumed `6s-8s` per ten `Variable` canonical rows. Current branch now prunes `.yarn` plus Yarn Berry Plug'n'Play loader files (`.pnp.cjs`, `.pnp.loader.mjs`) in default native discovery so generated package-manager bundles do not enter parsing, materialization, or graph projection.
- the `.yarn`-pruned full-corpus run progressed to roughly `620/896` repositories and failed after `47m12s` on `semantic_entity_materialization` with only `Function rows=2`; replaying that same statement against the stopped graph completed quickly. The current branch therefore treats this as contention/coordination evidence, not another batch-size problem: reducer writes now pass `PCG_CANONICAL_WRITE_TIMEOUT` through Neo4j-driver `tx_timeout` metadata just like the ingester already did, so the NornicDB server sees the same deadline as PCG's client context. NornicDB source review confirmed snapshot isolation and commit-time conflict detection are expected behavior, so the upstream follow-up is now `orneryd/NornicDB#120`, which maps MVCC conflict/deadlock errors to Neo4j transient transaction codes at the Bolt layer rather than serializing all PCG graph writes.
- the next full-corpus pass exposed the current IaC-heavy hot path before failure: `K8sResource` canonical writes were already at `rows=1` and one grouped statement, but the one-row `UNWIND ... MATCH File ... MERGE K8sResource ... MERGE CONTAINS` shape repeatedly cost roughly `3.2s-4.1s` under concurrent projection. Because the row and group caps are already minimal, the current branch now routes those one-row file-scoped inline-containment writes through the existing singleton parameterized execute-only statement shape instead of another tuning knob.
- `orneryd/NornicDB#120` has expanded from conflict-code mapping into the current upstream compatibility branch for this full-corpus lane. It now also shares the `nodeLookupCache` mutex across transaction clones, fixing the `fatal error: concurrent map writes` crash seen in the first 2026-04-26 remote full-corpus pass, and teaches NornicDB's generalized `UNWIND/MATCH/MERGE` batch hot path to accept named relationship variables with `SET rel.*`. That last fix keeps PCG's file-scoped entity-containment statement out of the generic fallback path that previously failed on source text containing `REMOVE`.
- the first `#120`-only full-corpus lane was stopped because it did not include PR `#119`'s SQL-edge hot path, so it was not the combined evidence PCG needs before promotion. The fork `main` was also realigned with `orneryd/main` after confirming merged PRs `#107`, `#115`, `#116`, and `#118` already represent the old fork-main patch content upstream.
- the current patched-binary evidence lane uses a combined NornicDB branch (`linuxdynasty/NornicDB:pcg-119-120-combined`, commit `86e78f1`) that stacks `#119` and `#120` over `orneryd/main`. Local and remote NornicDB focused gates passed with `go test -tags 'noui nolocalllm' ./pkg/cypher ./pkg/bolt ./pkg/server ./pkg/neo4jcompat -count=1`, and the remote headless binary was rebuilt from that exact commit at `/home/ubuntu/os-repos/NornicDB/bin/nornicdb-headless-pcg-119-120-combined`.
- the combined binary completed the `/home/ubuntu/pcg-test-repos` 23-repo authoritative lane in `80s` after passing the self-repo lane in `20s` and the focused Crossplane lane in `5s` with final `Health: healthy`, empty queue, and no dead letters. The shutdown emitted expected `context canceled` projection logs after the harness stopped the already-healthy owner; those are not counted as run failures.
- the superseded full-corpus lane `/tmp/pcg-perf-20260426T124838Z-119-120-full` used PCG `323b6b53` and NornicDB `86e78f1`. It passed the self-repo warmup in `20s`, passed focused Crossplane in `5s`, and at the early 896-repo checkpoint was progressing with projector `succeeded=63`, reducer `succeeded=455`, `dead_letter=0`, and no overdue claims. Follow-up drain-gate review showed the old harness could combine early healthy status with later collector completion, so this lane is valid throughput/activation evidence but not a complete projection-drain proof.
- live inspection of that full-corpus lane found a PCG flow-shape issue independent of NornicDB Cypher compatibility: local-host ingester commits were still doing per-new-repo relationship backfill inside the repository commit transaction. On a first-generation corpus scan every repo is new, so that repeats a corpus-wide `latest relationship facts` scan hundreds of times. Current branch adds a collector batch-drain hook and wires ingester/local-host collection to skip per-commit backfill, then run one deferred `BackfillAllRelationshipEvidence` plus `ReopenDeploymentMappingWorkItems` after the changed-repo batch drains. Focused tests `TestServiceRunCallsAfterBatchDrainedOnceAfterCommittedBatch` and `TestBuildIngesterCollectorServiceDefersRelationshipBackfillToBatchDrain` lock this in.
- the corrected drain-gate lane with PCG `56d8f9c8` and NornicDB `86e78f1` drained self-repo in `76s` and focused Crossplane in `10s`. The full `/home/ubuntu/pcg-e2e-full` lane stayed healthy-but-progressing with no dead letters and no overdue claims, but still had roughly `6k` queue items outstanding when stopped; the dominant visible backlog was reducer work, especially reopened `deployment_mapping`. This is consistent with the current first-generation queue shape: `896` repos times seven shared follow-up reducer domains can publish `6,272` reducer rows before accounting for completed or reopened work. That moves the next Chunk 3.5/4 task to reducer queue-shape and convergence throughput analysis under the NornicDB `workers=1` default before another full-corpus promotion claim.
- the first `PCG_REDUCER_WORKERS=2` A/B against the corrected drain gate preserved self-repo and focused Crossplane correctness, but the full corpus reported stalled health from overdue reducer claims rather than NornicDB write conflicts. The root cause is PCG's batch-claim window: the reducer could lease more intents than workers could start before the `60s` claim lease expired. Current branch therefore keeps Neo4j's broad batch-claim default but sets NornicDB's default `PCG_REDUCER_BATCH_CLAIM_SIZE` to `1` so a claimed reducer item means a worker can start it immediately.
- current branch also closes the missing patched-binary switch proof: `TestNornicDBBatchedEntityContainmentFullStackUsesCrossFileBatchedEntityRows` verifies the opt-in `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true` writer shape sends normal cross-file entities through one row-scoped batched statement and avoids file-scoped singleton execution. The queued full-corpus A/B run remains the performance gate before considering that switch for default promotion.

Current tuning plan:
- keep the safer `Annotation=10,Function=10,Variable=10,Module=10,ImplBlock=10` semantic row-cap baseline in code while we gather better evidence
- stop adding semantic label caps blindly: the schema-backed rerun proves the remaining wall was missing `uid` constraints, not label row width. Do not lower more PCG batch defaults without a fresh attribution profile showing a new bottleneck.
- treat reducer same-scope fencing as an ownership invariant, not a NornicDB-only timeout workaround; measure the next full-corpus run before adding any new batch knobs
- treat `PCG_REDUCER_WORKERS=1` as a stability baseline, not the final performance answer: the next benchmark should compare `PCG_REDUCER_WORKERS=2` with NornicDB's new single-item claim window against the corrected drain gate and NornicDB transient-conflict telemetry before deciding whether the worker default can safely move above one
- finish the combined `#119 + #120` full-corpus timing run, then either pin the release-backed NornicDB asset if upstream merges/releases both fixes or keep `PCG_NORNICDB_BINARY` / installer `--from` pointed at the combined branch binary for continued evaluation.
- keep the default NornicDB graph write budget at `30s`: the full-corpus timing run proved `15s` is too tight under production-scale local_authoritative concurrency, while `30s` still exposed the real `Annotation rows=500` statement-shape issue instead of hiding it. Timeout errors must continue to name `PCG_CANONICAL_WRITE_TIMEOUT` and include the statement summary, and both ingester/projector and reducer graph writers must send the same budget as Bolt `tx_timeout` metadata.
- keep rebuilding dogfood NornicDB headless binaries directly from upstream `main` for release-backed fixes such as merged PRs `#115`, `#116`, and `#118`; use the combined `#119 + #120` branch binary explicitly via `PCG_NORNICDB_BINARY` / installer `--from` for the active full-corpus compatibility lane until both PRs merge and a release asset is pinned
- only promote the patched lane after the NornicDB fixes are release-backed and pinned; until then, keep the pinned release on the safe file-scoped combined write and use `PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT=true` only for patched-binary evaluation
- keep dead-code truth labeled `derived`; the bounded policy buffer makes small-limit CLI output useful again, but broader root modeling is still required before promoting dead-code from derived to exact
- keep NornicDB call-chain and transitive relationship reads on bounded BFS until upstream proves parameterized `shortestPath` endpoint anchors and projected map collection behave like Neo4j on the PCG query corpus
- bundle future small heuristic changes with their safety gate when they are one logical fix, so rollback/bisect history tracks the behavioral unit rather than the order in which the concern was discovered
- treat the growing `PCG_NORNICDB_*` surface as an operator contract: keep the consolidated [NornicDB Tuning](../reference/nornicdb-tuning.md) page current, and add new phase-specific knobs only after logs prove the existing phase/label controls do not describe the bottleneck
- watch future heavy phases such as call edges, infra edges, and other shared reducer domains, but do not pre-create tuning knobs for them until repo-scale evidence names the phase, row count, grouped statement count, and timeout shape

---

## Executive Summary

This plan implements a local-first developer workflow without creating a second
authoritative graph product.

The work is organized around one principle:

- lightweight local mode should be excellent for code lookup and code
  comprehension
- authoritative graph truth should remain owned by the full local stack and
  production runtime path

The implementation is therefore split into six chunks:

1. define the capability contract and truth labels
2. make query surfaces depend on capability ports instead of backend brands
3. ship the lightweight local code-intelligence host
4. harden authoritative graph-backed code analysis in full local stack and prod
5. add backend conformance testing before any new graph backend is declared
   supported
6. add OCI-packaged collector plugin seams at the fact-emission boundary

This keeps production risk bounded while still giving developers the local
stdio MCP workflow they want.

## Success Criteria

### Developer experience

- a developer can install one `pcg` binary and use local stdio MCP without
  Docker for code-intelligence queries
- local mode supports single-repo and monofolder indexing
- local mode is explicit when an answer is `exact`, `derived`, or `fallback`

### Production safety

- the deployed runtime contract remains split by ownership
- no production query or reducer feature regresses because of local-mode work
- service-profile runtime tests continue to pass unchanged

### Architecture

- API, MCP, projector, reducer, and query layers depend on capability ports
  instead of concrete backend brands where practical
- backend conformance tests exist before any alternate graph backend is called
  supported

### Extensibility

- new collectors can be packaged as OCI artifacts and emit facts through a
  stable plugin contract

---

## Query Capability Matrix

This matrix is the contract the implementation should target.

| Capability | Lightweight local | Full local stack | Production |
| --- | --- | --- | --- |
| Exact symbol lookup | Yes | Yes | Yes |
| Fuzzy symbol search | Yes | Yes | Yes |
| Variable lookup | Yes | Yes | Yes |
| Code / comment / docstring search | Yes | Yes | Yes |
| Decorator / annotation search | Yes | Yes | Yes |
| Argument-name search | Yes | Yes | Yes |
| Methods on class | Yes | Yes | Yes |
| Import / reference discovery | Yes | Yes | Yes |
| Inheritance / implementation discovery | Yes, when semantic facts suffice | Yes | Yes |
| Complexity and hotspot queries | Yes | Yes | Yes |
| Direct callers / callees | Derived or exact only if proven | Yes | Yes |
| Transitive callers / callees | No promise unless authoritative graph exists | Yes | Yes |
| Call-chain path tracing | No promise unless authoritative graph exists | Yes | Yes |
| Dead code | No promise unless authoritative graph exists | Yes | Yes |
| Code + infra blast radius | Limited | Yes | Yes |

---

## Chunk 1: Capability Contract And Truth Labels

### Goal

Define the product contract before changing more runtime behavior.

### Work

- introduce common truth labels across CLI, MCP, and HTTP:
  - `exact`
  - `derived`
  - `fallback`
- add one shared truth-level type and response field rather than scattered
  prose-only fallback strings
- define a structured unsupported-capability error for high-authority queries
  that lightweight local mode cannot answer correctly
- document which queries belong to:
  - `CodeSearch`
  - `SymbolGraph`
  - `CallGraph`
  - `CodeQuality`
  - `PlatformImpact`
- update API/MCP/CLI docs to reflect capability semantics rather than backend
  assumptions

### Likely touch points

- `docs/docs/why-pcg.md`
- `docs/docs/reference/http-api.md`
- `docs/docs/guides/mcp-guide.md`
- `docs/docs/reference/truth-label-protocol.md`
- `docs/docs/reference/capability-conformance-spec.md`
- `specs/capability-matrix.v1.yaml`
- `go/internal/query/openapi*.go`
- MCP tool descriptors and response payload structs

### Verification

- focused query/API tests for new truth labels
- strict docs build

---

## Chunk 2: Capability Ports Instead Of Backend Brands

### Goal

Reduce direct dependency on `Neo4jReader` and backend-specific wiring in the
read path.

These ports do not exist today as named interfaces. This chunk is net-new
interface extraction, not a move to an already-portable design.

### Work

- extract or tighten the read-side storage-seam interfaces first:
  - `GraphQuery`
  - `ContentStore`
- keep higher-order capability groupings such as `CodeSearch`,
  `SymbolGraph`, and `CallGraph` as follow-on interfaces only if adapter
  tests show that the storage-seam ports are too coarse
- move API and MCP construction toward these ports rather than concrete backend
  readers
- keep the existing service runtime behavior the same while making backend
  swaps a wiring concern
- keep wire compatibility by supporting parallel old/new wiring during the
  extraction until contract tests prove equivalence

### Shared-state and concurrency considerations

- do not widen transaction scope accidentally while extracting interfaces
- keep graph writes and relational writes owned by their existing runtimes
- preserve reducer/projector ordering and current queue contracts

### Likely touch points

- `go/cmd/api/wiring.go`
- `go/cmd/mcp-server/wiring.go`
- `go/internal/query/*.go`
- `go/internal/projector/*.go`
- `go/internal/reducer/*.go`
- `go/internal/storage/*`

### Verification

- `cd go && go test ./internal/query ./cmd/api ./cmd/mcp-server -count=1`
- `cd go && go vet ./internal/query ./cmd/api ./cmd/mcp-server`
- contract tests proving old and new wiring return the same response shape

---

## Chunk 3: Lightweight Local Code Intelligence Host

### Goal

Ship a single-binary local host that gives developers a strong stdio MCP and
CLI story without requiring Docker.

### Work

- manage embedded local Postgres lifecycle inside `pcg`
- add a local host mode used by `pcg watch`, `pcg mcp stdio`, and local query
  commands
- persist local index state under a stable per-workspace data root
- define the local data-root spec: layout, version file, ownership lock,
  migration rules, and reset behavior
- support:
  - single repo
  - monofolder / multi-repo workspace
- expose the local code-intelligence tier:
  - definitions
  - search
  - methods
  - imports
  - inheritance where semantic facts suffice
  - complexity

### Workflow shape

1. file change or initial index enters local host
2. collector parses and emits facts
3. projector writes content/entity/search-support tables
4. query surfaces read those tables directly
5. stdio MCP serves the same query contract as CLI/API

### Shared-state inventory

- local Postgres data directory
- workspace ownership record
- local status/report state
- content/entity/query-support relational tables

### Concurrency plan

- one local host process owns the workspace data root
- second invocations use a lock protocol with stale-lock recovery and fail-fast
  behavior when safe attachment is not possible
- fsnotify events are debounced and coalesced to avoid parse storms
- collector and projector work stay bounded with explicit backpressure
- child runtime shutdown must be coordinated and observable
- no orphaned embedded Postgres process on `SIGINT` or host shutdown
- embedded Postgres crash recovery and stale data-root ownership must be
  exercised explicitly

### Telemetry

- local host lifecycle spans
- local Postgres startup/shutdown logs
- query truth-level counters
- local index freshness and queue/status metrics where applicable

### Likely touch points

- `go/cmd/pcg/*.go`
- `go/internal/runtime/*.go`
- `go/internal/storage/postgres/*.go`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/local-host-lifecycle.md`
- `docs/docs/reference/local-performance-envelope.md`
- local MCP startup and discovery code

### Verification

- focused CLI/runtime tests
- local lifecycle tests for clean shutdown
- perf-envelope smoke tests against the documented local targets
- manual smoke test for `pcg watch .` + `pcg mcp stdio`

---

## Chunk 3.5: NornicDB Laptop Sidecar And `local_authoritative`

### Goal

Add an explicit authoritative-local runtime contract without silently turning
it into lightweight mode.

### Work

- add `local_authoritative` runtime selection to the local host
- default laptop graph discovery and future install flow to
  `nornicdb-headless`, while allowing explicit opt-in to the larger full
  `nornicdb` binary
- persist profile and graph-backend metadata in `owner.json`
- reserve graph-sidecar paths inside the local workspace data root
- fail loudly when `local_authoritative` is requested before the graph sidecar
  lifecycle is wired
- add the graph-sidecar startup, health, and shutdown lifecycle behind the
  local host once the NornicDB adapter is ready
- add the first installer slice:
  `pcg install nornicdb --from <source> [--sha256 <hex>] [--force]`, which
  verifies a local binary, local tar archive, or URL-backed archive, copies
  the extracted binary to `${PCG_HOME}/bin/nornicdb-headless`, and records a
  managed install manifest without yet inventing a no-arg release selector

### First implementation slice

- add `graph/` to the local workspace layout
- add `profile`, `graph_backend`, and graph-sidecar metadata fields to
  `owner.json`
- make the local host resolve `PCG_QUERY_PROFILE` and `PCG_GRAPH_BACKEND`
  explicitly instead of hardcoding lightweight mode
- reject unsupported `local_authoritative` startup before workspace ownership
  or embedded Postgres boot so the failure is immediate and unambiguous

### Likely touch points

- `go/cmd/pcg/local_host.go`
- `go/internal/pcglocal/layout.go`
- `go/internal/pcglocal/owner.go`
- `go/cmd/api/wiring.go`
- `go/cmd/mcp-server/wiring.go`
- `go/cmd/ingester/local_lightweight.go`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/local-host-lifecycle.md`
- `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`

### Verification

- focused local-host tests for profile/backend resolution
- owner-record round-trip tests including graph metadata
- layout tests proving a stable `graph/` path per workspace
- manual proof that `local_authoritative` fails loudly until sidecar wiring is
  implemented
- opt-in syntax gate against a real NornicDB binary:
  `PCG_NORNICDB_BINARY=/tmp/nornicdb-headless go test ./cmd/pcg -run TestNornicDBSyntaxVerification -count=1 -v`.
  The current release-backed NornicDB binary accepts the multi-label fulltext
  procedure form and `COLLECT(DISTINCT {map literal})`, but still rejects PCG's
  composite `IS UNIQUE` schema syntax.
- opt-in workaround gate against the same binary:
  `PCG_NORNICDB_BINARY=/tmp/nornicdb-headless go test ./cmd/pcg -run TestNornicDBCompatibilityWorkarounds -count=1 -v`.
  The 2026-04-22 run also passed composite `IS NODE KEY` and the multi-label
  fulltext procedure form. `IS NODE KEY` remains a syntax-compatible option,
  but PCG does not use it for sparse semantic labels because it makes every
  participating property required.
- graph schema dialect gate:
  `PCG_NORNICDB_BINARY=/tmp/nornicdb-headless go test ./cmd/pcg -run TestNornicDBSchemaAdapterVerification -count=1 -v`.
  The current branch passes after routing schema bootstrap through the
  backend-specific renderer: Neo4j keeps composite `IS UNIQUE`, while
  NornicDB skips unsupported composite uniqueness DDL, keeps single-property
  `uid` uniqueness constraints for canonical merge identity, and still skips
  Neo4j's multi-label fulltext fallback.
- installer gate:
  `go test ./cmd/pcg -run TestInstallNornicDB -count=1`.
  The current branch run passes local-file copy, checksum mismatch rejection,
  JSON output, and managed-binary discovery preference.
- graph log CLI gate:
  `go test ./cmd/pcg -run TestRunGraphLogs -count=1`.
  The current branch run passes workspace-root resolution, log streaming, and
  missing-log guidance without taking ownership of the workspace.
- owner-aware graph stop gate:
  `go test ./cmd/pcg -run TestGraphStop -count=1`.
  The current branch run passes live-owner signaling, stale graph direct stop,
  and lightweight-owner rejection without introducing a second graph owner.
- graph start CLI gate:
  `go test ./cmd/pcg -run TestRunGraphStart -count=1`.
  The current branch run passes foreground exec into `local-host watch` with
  `PCG_QUERY_PROFILE=local_authoritative` and `PCG_GRAPH_BACKEND=nornicdb`.
- graph upgrade CLI gate:
  `go test ./cmd/pcg -run TestRunGraphUpgrade -count=1`.
  The current branch run passes stopped-owner local-file replacement and
  rejects upgrade while a workspace owner or graph backend is still healthy.
- local-authoritative startup perf gate:
  `PCG_NORNICDB_BINARY=/tmp/pcg-bare-install-smoke/bin/nornicdb-headless PCG_LOCAL_AUTHORITATIVE_PERF=true go test ./cmd/pcg -run TestLocalAuthoritativeStartupEnvelope -count=1 -v`.
  The 2026-04-23 run measured cold start `9.045253708s` and warm restart
  `490.996625ms` at the owner-record plus ingester handoff, both within the
  documented `local_authoritative` startup envelope.
- manual local-authoritative lifecycle smoke:
  `PCG_HOME=/tmp/pcg-local-authoritative-smoke ./go/bin/pcg install nornicdb --from /tmp/nornicdb-headless`;
  `./go/bin/pcg graph start --workspace-root <repo>`;
  `./go/bin/pcg graph status --workspace-root <repo>` showed
  `profile=local_authoritative`, `graph_backend=nornicdb`, and
  `graph_running=true`; `./go/bin/pcg graph logs --workspace-root <repo>`
  printed the NornicDB sidecar log; `./go/bin/pcg graph stop --workspace-root <repo>`
  cleanly stopped the owner; final status showed `owner_present=false` and
  `graph_running=false`.
- manual local-authoritative MCP smoke:
  `PCG_HOME=/tmp/pcg-local-authoritative-e2e2 PCG_CANONICAL_WRITE_TIMEOUT=2s ./go/bin/pcg graph start --workspace-root <repo>`;
  `./go/bin/pcg mcp start --workspace-root <repo>`;
  MCP `search_file_content` for `startManagedLocalGraph` returned two Go
  files from `postgres_content_store`; MCP `find_code` returned the
  `startManagedLocalGraph` function with `truth.profile=local_authoritative`
  and `truth.basis=content_index`; `get_index_status` reported degraded graph
  projection after a bounded NornicDB canonical write timeout; `pcg graph stop`
  cleanly stopped the owner and final status showed `owner_present=false`.

---

## Chunk 4: Authoritative Graph Analysis Hardening

### Goal

Ensure the high-value graph-backed code-intelligence surface is solid in full
local stack and production.

### Work

- harden direct caller/callee queries
- harden transitive caller/callee queries
- harden call-chain path queries
- define and implement dead-code policy based on explicit reachability roots
- publish a dead-code reachability spec that covers framework callbacks,
  background workers, SQL entrypoints, and language/framework-specific roots
- ensure reducers materialize the graph truth these queries require

### Required modeling decisions

- what counts as a root for dead-code analysis:
  - `main`
  - HTTP handlers
  - CLI commands
  - framework callbacks
  - tests excluded or not
- how dynamic dispatch and reflection are represented
- how cross-file and cross-repo code calls are admitted

### Conflict-domain reasoning

- reducer acceptance and graph-write phases remain the authoritative bottleneck
- code-call and semantic-entity materialization must not rely on timing or
  watch-loop luck
- completion must be provable from durable state, not inferred from log order

### Likely touch points

- `go/internal/reducer/code_call_*`
- `go/internal/query/code_*`
- `go/internal/storage/neo4j/*`
- `docs/docs/reference/dead-code-reachability-spec.md`
- compose verification scripts for graph-backed queries

### Verification

- positive, negative, and ambiguous truth tests
- full-stack compose validation for callers/callees/path/dead-code
- direct query/API verification against a fresh run
- compose-backed end-to-end validation is mandatory for this chunk

---

## Chunk 5: Backend Conformance Suite

### Goal

Make future graph backend evaluation safe and evidence-based.

### Work

- define backend capability matrix:
  - canonical writes
  - direct graph reads
  - path traversal
  - full-text support
  - dead-code readiness
  - performance envelope
- add a conformance harness that runs the same query corpus against any
  backend adapter under test
- classify backends as:
  - unsupported
  - experimental
  - local-only
  - production-capable
- include deterministic read-shape checks plus write-semantics tests for
  ordering, MERGE/upsert behavior, and transaction visibility

### Important rule

No backend should be described as supported because it "speaks Cypher" alone.

### Likely touch points

- backend test harnesses
- adapter packages
- docs describing backend support status

### Verification

- deterministic conformance runs in CI for supported adapters
- explicit failure reports for missing capability classes

---

## Chunk 6: OCI Collector Plugin Contract

### Goal

Let developers add new collectors without patching the core runtime by hand.

### Work

- define a collector plugin contract at the fact-emission seam
- publish fact-schema versioning and compatibility rules before plugin loading
  work starts
- specify plugin metadata:
  - supported source kinds
  - emitted fact kinds and versions
  - compatibility range
  - packaging metadata
- support OCI artifact distribution for collector plugins
- keep reducers and graph writers unchanged by plugin packaging

### Design rule

Collectors emit versioned facts. They do not write canonical graph truth
directly.

Plugin loading requires an explicit trust model: signing or allowlisting,
provenance checks, and hard failure on incompatible fact-schema versions.

Chunk 6 must not begin until the fact-schema-versioning and plugin-trust-model
specs are frozen.

### Likely touch points

- collector runtime loading
- fact envelope/version negotiation
- `docs/docs/reference/fact-schema-versioning.md`
- `docs/docs/reference/plugin-trust-model.md`
- plugin documentation and packaging tooling

### Verification

- plugin load tests
- fact compatibility tests
- OCI packaging and fetch smoke tests

---

## Observability And Reliability Requirements

Every chunk above must preserve the repo's operating priorities:

1. accuracy
2. performance/concurrency
3. reliability

Required observability themes:

- query truth level must be visible
- local-host process ownership and shutdown must be inspectable
- reducer convergence must be diagnosable from durable state and telemetry
- backend selection must be explicit in logs and spans

Suggested telemetry dimensions:

- `storage_profile`
- `graph_backend`
- `truth_level`
- `workspace_id`
- `repo_scope`

---

## Non-Goals

- replacing Neo4j in production during this implementation
- replacing Postgres in the service profile
- pretending lightweight local mode has full authoritative graph parity
- introducing a new query language
- moving graph or reducer writes into collector plugins
- cross-workspace shared local data roots

---

## Verification Matrix

Minimum verification by work area:

- docs or product-contract changes:
  - `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`
- query contract changes:
  - `cd go && go test ./internal/query ./cmd/api ./cmd/mcp-server -count=1`
  - `cd go && go vet ./internal/query ./cmd/api ./cmd/mcp-server`
- runtime/local-host changes:
  - `cd go && go test ./cmd/pcg ./internal/runtime ./internal/status -count=1`
- facts/reducer/query truth changes:
  - `cd go && go test ./internal/projector ./internal/reducer ./internal/storage/postgres -count=1`
  - compose-backed query verification when graph truth is affected
- Chunk 4 compose end-to-end gate:
  - callers/callees/call-chain/dead-code must pass against a fresh full-stack run
- repo hygiene:
  - `git diff --check`

---

## Implementation Order

The recommended order is:

1. capability contract and truth labels
2. capability-port extraction
3. lightweight local host
4. authoritative graph query hardening
5. backend conformance harness
6. OCI collector plugin seam

This order is deliberate:

- it avoids building local mode on top of unstable query semantics
- it avoids backend experiments before the capability boundaries exist
- it protects production by keeping the authoritative path intact while local
  workflows improve
