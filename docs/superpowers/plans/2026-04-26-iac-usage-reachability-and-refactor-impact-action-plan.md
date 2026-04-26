# IaC Usage Reachability And Refactor Impact Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `karpathy-guidelines` and `google-go-best-practices` for every Go change.

**Goal:** Implement the IaC usage, reachability, integrity, and refactor-impact graph from the related ADR without weakening PCG truth labels or reducer concurrency.

**Architecture:** Add durable IaC reference facts first, then materialize typed usage edges through reducer-owned phases, and expose query surfaces only after parser, projector, reducer, and query contracts have tests. Keep the first release static and source-backed; renderer-backed proof is opt-in and must report partial coverage when unavailable.

**Tech Stack:** Go, PostgreSQL fact store, graph adapter ports, Neo4j/NornicDB-compatible query paths, OTEL telemetry, MkDocs

**Related ADR:** `docs/docs/adrs/2026-04-24-iac-usage-reachability-and-refactor-impact.md`

---

## Core Goals

1. **Accuracy:** never label IaC dead unless root reachability and domain semantics support it.
2. **Concurrency:** reducer work is bounded by repo/generation/family and must not serialize unrelated repositories.
3. **Speed:** use batched reference extraction, batched fact writes, and bounded graph traversals.
4. **Instrumentation:** every parser, reducer, and query phase emits operator-visible spans, counters, histograms, and structured limitations.

## Assumptions

1. Phase 0 neighborhood work can start with existing code and content relationships, but exact IaC deadness waits for durable usage facts.
2. Existing content relationship builders are evidence sources, not the final durable usage model.
3. Renderer-backed Helm/Kustomize validation is optional in the first pass and must not block parser-only results.

## Task 1: Freeze IaC Usage Fact Contracts

**Files:**
- Modify: `go/internal/facts/models.go`
- Modify: `go/internal/facts/models_test.go`
- Create: `go/internal/facts/iac_usage.go`
- Create: `go/internal/facts/iac_usage_test.go`
- Modify: `docs/docs/reference/fact-envelope-reference.md`

1. Write failing tests for `IaCReferenceFact`, `IaCFindingFact`, stable IDs, required scope fields, and confidence values.
   -> verify: `cd go && go test ./internal/facts -run 'TestIaC' -count=1` fails on missing types.
2. Implement minimal fact structs with stable IDs keyed by repo, generation, source path, source selector, target key, reference kind, and family.
   -> verify: `cd go && go test ./internal/facts -run 'TestIaC' -count=1` passes.
3. Document the fact envelope examples.
   -> verify: `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`.
4. Commit.
   -> verify: `git status --short` shows a clean worktree after commit.

## Task 2: Add Terraform And Terragrunt Reference Extraction

**Files:**
- Modify: `go/internal/parser/hcl_language.go`
- Modify: `go/internal/parser/hcl_terragrunt_helpers.go`
- Modify: `go/internal/parser/hcl_terragrunt_expression_helpers.go`
- Modify: `go/internal/parser/hcl_terraform_test.go`
- Modify: `go/internal/parser/hcl_terragrunt_test.go`
- Create: `go/internal/parser/hcl_iac_references_test.go`

1. Write failing parser tests for `var`, `local`, `data`, `resource`, `module`, `module.output`, `depends_on`, `count`, `for_each`, `source`, `file`, `templatefile`, and Terragrunt `config_path`.
   -> verify: `cd go && go test ./internal/parser -run 'TestHCLIaCReference' -count=1` fails on missing references.
2. Implement HCL traversal with `context.Context` only where request-scoped work is added; keep extraction deterministic and side-effect free.
   -> verify: `cd go && go test ./internal/parser -run 'TestHCLIaCReference|TestTerraform|TestTerragrunt' -count=1`.
3. Add parser telemetry counters for extracted references by family/kind without path labels.
   -> verify: telemetry contract tests assert no high-cardinality path labels.
4. Commit.
   -> verify: focused parser tests pass after commit.

## Task 3: Promote Kustomize, ArgoCD, Helm, And Kubernetes Evidence To Usage Edges

**Files:**
- Modify: `go/internal/query/content_relationships_kustomize_test.go`
- Modify: `go/internal/query/content_relationships_kustomize_deploy_test.go`
- Modify: `go/internal/query/content_relationships_argocd_test.go`
- Modify: `go/internal/query/content_relationships_k8s_test.go`
- Create: `go/internal/parser/helm_iac_references_test.go`
- Create: `go/internal/parser/kubernetes_iac_references_test.go`
- Create: `go/internal/relationships/iac_usage_evidence.go`
- Create: `go/internal/relationships/iac_usage_evidence_test.go`

1. Write failing evidence tests that convert existing content relationship metadata into normalized usage-reference candidates.
   -> verify: `cd go && go test ./internal/relationships -run 'TestIaCUsageEvidence' -count=1` fails.
2. Implement conversion helpers for Kustomize resources/bases/components/patches, ArgoCD source paths, Helm values/templates, and Kubernetes selectors/config refs.
   -> verify: relationship tests and the touched query content tests pass.
3. Keep uncertain Kubernetes orphan checks as `suspicious_orphan`, not `unused_definition`.
   -> verify: tests assert conservative finding classes.
4. Commit.
   -> verify: `cd go && go test ./internal/relationships ./internal/query -run 'IaC|Kustomize|ArgoCD|Helm|K8s' -count=1`.

## Task 4: Persist And Resolve IaC Usage Edges

**Files:**
- Create: `go/internal/storage/postgres/iac_usage_facts.go`
- Create: `go/internal/storage/postgres/iac_usage_facts_test.go`
- Create: `go/internal/reducer/iac_usage_materialization.go`
- Create: `go/internal/reducer/iac_usage_materialization_test.go`
- Modify: `go/internal/reducer/defaults.go`
- Modify: `go/cmd/reducer/main.go`

1. Write failing Postgres tests for idempotent upsert, generation scoping, and batched lookup.
   -> verify: `cd go && go test ./internal/storage/postgres -run 'TestIaCUsage' -count=1` fails.
2. Write failing reducer tests for concurrent-safe materialization across distinct repo/generation partitions.
   -> verify: `cd go && go test ./internal/reducer -run 'TestIaCUsage' -count=1` fails.
3. Implement batched fact persistence and reducer materialization without global locks.
   -> verify: focused storage and reducer tests pass.
4. Add reducer spans, duration histograms, extracted/resolved/unresolved counters, and failure-class logs.
   -> verify: observability tests assert metric names and low-cardinality labels.
5. Commit.
   -> verify: `cd go && go test ./internal/storage/postgres ./internal/reducer -run 'IaCUsage|Observability' -count=1`.

## Task 5: Add Dead IaC, Integrity, And Refactor Impact Queries

**Files:**
- Create: `go/internal/query/iac_usage.go`
- Create: `go/internal/query/iac_usage_test.go`
- Modify: `go/internal/query/openapi.go`
- Create: `go/internal/query/openapi_paths_iac.go`
- Modify: `docs/docs/reference/http-api.md`
- Modify: `docs/docs/reference/mcp-reference.md`

1. Write failing query tests for `dead_iac`, `impact`, `integrity`, and `relationships` responses with exact, derived, and ambiguous truth labels.
   -> verify: `cd go && go test ./internal/query -run 'TestIaCUsage' -count=1` fails.
2. Implement handlers behind graph/query ports, returning unsupported capability envelopes when graph support is unavailable.
   -> verify: focused query tests pass.
3. Add OpenAPI and docs examples.
   -> verify: `cd go && go test ./internal/query -run 'TestServeOpenAPI|TestIaCUsage' -count=1`.
4. Commit.
   -> verify: docs and query tests pass after commit.

## Task 6: MCP, CLI, And Local-Authoritative Proof

**Files:**
- Modify: `go/internal/mcp/dispatch.go`
- Modify: `go/internal/mcp/tools_codebase.go`
- Modify: `go/internal/mcp/tools_context.go`
- Modify: `go/internal/mcp/tools_test.go`
- Modify: `go/internal/mcp/dispatch_test.go`
- Modify: `go/cmd/pcg/analyze.go`
- Modify: `go/cmd/pcg/analyze_test.go`
- Modify: `docs/docs/reference/cli-reference.md`
- Modify: `docs/docs/guides/mcp-guide.md`

1. Write failing MCP and CLI routing tests for `find_dead_iac`, `trace_iac_impact`, `find_broken_iac_references`, and `get_iac_relationships`.
   -> verify: focused MCP/CLI tests fail.
2. Implement route mappings and CLI commands with exact JSON output passthrough.
   -> verify: `cd go && go test ./internal/mcp ./cmd/pcg -run 'IaC|Analyze' -count=1`.
3. Run strict docs and the smallest local-authoritative or compose proof that covers the touched IaC family before claiming exact graph-backed behavior.
   -> verify: proof command output is captured in the implementation PR notes.
4. Commit.
   -> verify: `git status --short` is clean.

## Final Verification

Run:

```bash
cd go && go test ./internal/facts ./internal/parser ./internal/relationships ./internal/storage/postgres ./internal/reducer ./internal/query ./internal/mcp ./cmd/pcg -count=1
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

Expected: all commands exit 0. If any test is skipped because it requires compose or local-authoritative services, document the exact reason and the replacement proof.
