# Cross-Repo Contract Bridge And Service Dependency Graph Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `karpathy-guidelines` and `google-go-best-practices` for every Go change.

**Goal:** Add a conservative cross-repo contract bridge for HTTP, gRPC, events, schemas, generated clients, and shared libraries, then feed contract edges into dependency neighborhoods and change-impact summaries.

**Architecture:** Start with normalized contract identities and exact/derived matching rules. Persist provider and consumer evidence as durable facts, resolve matches in reducer-owned batches, and expose contract impact only with truth labels and ambiguity reasons.

**Tech Stack:** Go parser/extractor packages, PostgreSQL facts, reducer materialization, graph/query ports, MCP/CLI/docs, OTEL telemetry

**Related spec:** `docs/superpowers/specs/2026-04-26-cross-repo-contract-bridge-and-service-dependency-graph-design.md`
**Related ADR:** `docs/docs/adrs/2026-04-24-iac-usage-reachability-and-refactor-impact.md`

---

## Core Goals

1. **Accuracy:** exact matches require stable contract identities; string-only evidence stays derived or unresolved.
2. **Concurrency:** contract resolution batches by generation, family, and identity partition; no global resolver lock.
3. **Speed:** normalize once, index by contract key, and cap high-fanout query expansion.
4. **Instrumentation:** emit extraction, resolution, ambiguity, fanout, and query metrics without route/topic/path labels.

## Task 1: Define Contract Identity Types And Normalization

**Files:**
- Create: `go/internal/contracts/doc.go`
- Create: `go/internal/contracts/identity.go`
- Create: `go/internal/contracts/identity_test.go`
- Create: `go/internal/contracts/http.go`
- Create: `go/internal/contracts/grpc.go`
- Create: `go/internal/contracts/events.go`

1. Write failing table tests for HTTP route normalization, gRPC package/service/method keys, event topic keys, schema keys, and library keys.
   -> verify: `cd go && go test ./internal/contracts -run 'Test.*Identity' -count=1` fails.
2. Implement small concrete types with exported doc comments and no premature interfaces.
   -> verify: identity tests pass.
3. Add exact, derived, ambiguous, and unresolved match confidence values.
   -> verify: tests assert invalid values fail validation.
4. Commit.
   -> verify: `cd go && go test ./internal/contracts -count=1`.

## Task 2: Add Durable Contract Evidence Facts

**Files:**
- Modify: `go/internal/facts/models.go`
- Modify: `go/internal/facts/models_test.go`
- Create: `go/internal/facts/contract_evidence.go`
- Create: `go/internal/facts/contract_evidence_test.go`
- Modify: `docs/docs/reference/fact-envelope-reference.md`

1. Write failing tests for provider/consumer fact validation, stable IDs, source spans, generation scope, and role values.
   -> verify: `cd go && go test ./internal/facts -run 'TestContractEvidence' -count=1` fails.
2. Implement fact structs and stable IDs based on family, normalized key, role, repo, generation, source path, and source selector.
   -> verify: focused facts tests pass.
3. Document fact examples and truth fields.
   -> verify: strict docs build passes.
4. Commit.
   -> verify: worktree clean after commit.

## Task 3: Extract HTTP And OpenAPI Provider/Consumer Evidence

**Files:**
- Create: `go/internal/relationships/contract_http_evidence.go`
- Create: `go/internal/relationships/contract_http_evidence_test.go`
- Modify: `go/internal/parser/go_language_test.go`
- Modify: `go/internal/parser/engine_javascript_semantics_test.go`
- Modify: `go/internal/parser/engine_typescript_advanced_semantics_test.go`
- Modify: `go/internal/parser/engine_python_semantics_test.go`
- Create: `tests/fixtures/ecosystems/contract_http_basic/` fixture files if needed

1. Write failing relationship tests for OpenAPI provider paths, framework route metadata, generated-client references, and explicit typed HTTP consumers.
   -> verify: `cd go && go test ./internal/relationships -run 'TestHTTPContractEvidence' -count=1` fails.
2. Implement conservative HTTP evidence extraction from existing metadata and specs; leave raw string URLs derived.
   -> verify: HTTP contract evidence tests pass.
3. Add negative tests proving wildcard/prefix/string-only evidence is not exact.
   -> verify: negative tests pass.
4. Commit.
   -> verify: `cd go && go test ./internal/relationships -run 'Contract|HTTP' -count=1`.

## Task 4: Extract gRPC, Event, Schema, And Library Evidence

**Files:**
- Create: `go/internal/relationships/contract_grpc_evidence.go`
- Create: `go/internal/relationships/contract_event_evidence.go`
- Create: `go/internal/relationships/contract_schema_evidence.go`
- Create: `go/internal/relationships/contract_library_evidence.go`
- Create: matching `*_test.go` files

1. Write failing tests for proto provider/consumer evidence, topic producer/consumer evidence, schema artifact references, generated-client provenance, and shared-library consumers.
   -> verify: focused relationship tests fail.
2. Implement extraction using existing parser metadata first; add parser metadata only when a test proves it is missing.
   -> verify: focused tests pass.
3. Keep generated-code evidence linked to source schema provenance when available.
   -> verify: tests assert provenance fields.
4. Commit.
   -> verify: `cd go && go test ./internal/relationships ./internal/parser -run 'Contract|Proto|Event|Schema|Library' -count=1`.

## Task 5: Persist And Resolve Provider/Consumer Matches

**Files:**
- Create: `go/internal/storage/postgres/contract_evidence_facts.go`
- Create: `go/internal/storage/postgres/contract_evidence_facts_test.go`
- Create: `go/internal/reducer/contract_resolution.go`
- Create: `go/internal/reducer/contract_resolution_test.go`
- Modify: `go/internal/reducer/defaults.go`
- Modify: `go/cmd/reducer/main.go`

1. Write failing storage tests for idempotent upsert, family/key lookup, generation scoping, and high-fanout pagination.
   -> verify: storage tests fail.
2. Write failing reducer tests for exact, derived, ambiguous, and unresolved matches across two repositories.
   -> verify: reducer tests fail.
3. Implement partitioned resolution by family and normalized key, with no global mutex and bounded batch sizes.
   -> verify: storage and reducer tests pass.
4. Add contract resolution spans, counters, duration histograms, fanout counters, and ambiguity logs.
   -> verify: observability tests assert low-cardinality dimensions.
5. Commit.
   -> verify: `cd go && go test ./internal/storage/postgres ./internal/reducer -run 'Contract' -count=1`.

## Task 6: Feed Contract Edges Into Neighborhood And Change Impact

**Files:**
- Modify: `go/internal/query/graph_neighborhood.go`
- Modify: `go/internal/query/graph_neighborhood_ports.go`
- Modify: `go/internal/query/graph_neighborhood_types.go`
- Modify: `go/internal/query/change_impact.go`
- Create: `go/internal/query/contract_impact.go`
- Create: `go/internal/query/contract_impact_test.go`
- Modify: `go/internal/query/openapi_paths_graph.go`
- Modify: `go/internal/query/openapi_paths_impact.go`

1. Write failing query tests proving contract consumers appear in `Depended On By`, `Paths`, and `Blast Radius`.
   -> verify: focused query tests fail.
2. Implement contract readers through query ports and include exactness/ambiguity in response truth.
   -> verify: contract query tests pass.
3. Add changed-contract impact for route, proto, schema, topic, generated-client, and shared-library edits.
   -> verify: change-impact tests pass.
4. Commit.
   -> verify: `cd go && go test ./internal/query -run 'Contract|GraphNeighborhood|ChangeImpact' -count=1`.

## Task 7: Expose MCP, CLI, Docs, And Fixture Guidance

**Files:**
- Modify: `go/internal/mcp/dispatch.go`
- Modify: `go/internal/mcp/tools_codebase.go`
- Modify: `go/internal/mcp/tools_context.go`
- Modify: `go/internal/mcp/tools_test.go`
- Modify: `go/internal/mcp/dispatch_test.go`
- Modify: `go/cmd/pcg/analyze.go`
- Modify: `go/cmd/pcg/analyze_test.go`
- Modify: `docs/docs/reference/http-api.md`
- Modify: `docs/docs/reference/mcp-reference.md`
- Modify: `docs/docs/guides/fixture-ecosystems.md`

1. Write failing MCP and CLI tests for contract-aware dependency and impact queries.
   -> verify: focused MCP/CLI tests fail.
2. Implement route mappings and CLI wrappers without duplicating query logic.
   -> verify: focused MCP/CLI tests pass.
3. Document fixture requirements for provider/consumer corpora and ambiguity cases.
   -> verify: strict docs build passes.
4. Commit.
   -> verify: worktree clean after commit.

## Final Verification

Run:

```bash
cd go && go test ./internal/contracts ./internal/facts ./internal/relationships ./internal/storage/postgres ./internal/reducer ./internal/query ./internal/mcp ./cmd/pcg -count=1
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

Expected: all commands exit 0. Any skipped compatibility or compose checks must be recorded with the exact reason and a follow-up issue.
