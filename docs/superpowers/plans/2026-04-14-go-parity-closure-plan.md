# Go Parity Closure Plan

This plan closes the remaining feature-for-feature parity gaps after the
Python-to-Go runtime migration.

The branch is already structurally Go-owned. The remaining work is graph-surface
and end-to-end parity closure.

## Goal

Reach honest feature-for-feature parity with the old Python platform before any
new collector or source-family expansion begins.

## Execution Rules

- stay on the same branch and worktree
- no new ingestors before parity closure is complete
- treat parser extraction parity and graph/query-surface parity as separate bars
- use TDD for every code change
- keep docs current as each feature family closes
- update the language pages when a capability moves from `partial` or
  `unsupported` to `supported`

## Phase 0: Operator And Runtime Contract Closure

### Scope

Close the remaining non-parser platform gaps so the operator contract matches
the Go-owned runtime exactly.

### Primary gaps

- `pcg serve start` still advertises a combined API and MCP runtime even though
  MCP is a separate binary today
- API admin handlers exist in Go but are not fully mounted through `pcg-api`
- some docs still imply run-scoped index coverage endpoints that the generated
  OpenAPI does not currently expose
- status endpoint breadth may still be narrower than the final desired operator
  contract
- a few CLI flows are Go-owned but still thinner than the historical Python
  user experience

### Validation

- focused Go tests under `go/cmd/pcg`, `go/cmd/api`, `go/internal/query`, and
  `go/internal/status`
- OpenAPI verification
- compose-backed operator proof
- updated operator docs and parity audit

## Phase 1: SQL And Data-Intelligence Validation Closure

### Scope

Keep the SQL and dbt parity story honest by expanding validation maturity and
operator proof, not by pretending the remaining historical non-goals are
missing Go parity features.

### Primary gaps

- broader real-repo and end-to-end proof for compiled analytics models
- compose-backed proof that the current Go-owned runtime preserves the checked-in
  SQL/dbt fixture semantics
- docs and runbooks that clearly separate Python-era parity from optional
  post-parity enhancements

### Validation

- focused parser, materialization, and query verification
- compose-backed fixture verification
- updated SQL language page and parity audit

## Phase 2: High-Value Graph-Surface Parity

### Scope

Close the highest-value remaining graph-first and higher-level surfacing gaps
for the main application languages after the shared query outputs have already
become first-class.

### Families

- TypeScript: graph-first promotion for type aliases, decorators, generics
- TypeScript JSX: graph-first component/reference promotion and remaining alias
  surfacing
- Python: graph-first promotion for decorators, async flags, type annotations
- JavaScript: graph-first promotion for docstrings and fuller method-kind
  metadata
- Canonical call edges: broaden the new Go-owned `CALLS` materialization path
  from SCIP-backed edges and same-file generic-call proof into the remaining
  cross-file generic and long-tail parser families, then prove it end to end.
  The current same-file reducer proof now includes family-safe disambiguation
  for Swift receiver types, Ruby module/class scope, PHP receiver-qualified
  calls without unsafe bare-name fallback, and exact-only qualified Elixir
  matching. The current cross-file reducer proof now also covers JS/TS/TSX
  import-driven generic calls plus exact-qualified Swift/Ruby/Elixir/PHP
  static-style calls; Python module and `from` imports now close cross-file
  generic call proof honestly, and reducer proof now also covers repo-unique
  cross-file bare-name calls across the remaining parser-first long-tail
  families. The remaining call-edge gap is end-to-end query proof for those
  edges, especially `dead-code`, `call-chain`, and the still-stale
  `code/relationships` CLI/MCP contract

### Validation

- focused parser and persistence tests
- API/MCP/query proof where the old Python behavior surfaced these features
- reducer/collector proof for canonical `CALLS` materialization where the old
  Python behavior produced call-graph edges
- updated language pages and parity audit

## Phase 3: IaC And Deployment Semantics Parity

### Scope

Close the remaining infrastructure-language normalization gaps.

### Families

- Terraform: `terraform {}` block materialization if parity requires it
- Terragrunt: locals and inputs as queryable entities
- Kubernetes: labels
- ArgoCD: sync policy and ApplicationSet generator normalization
- CloudFormation: JSON-template parity
- Kustomize: base references

### Validation

- focused parser tests
- relationship and query-surface checks where applicable
- compose-backed proof for the impacted IaC ecosystems

## Phase 4: Long-Tail Language Parity

### Scope

Close the documented long-tail graph-surface gaps.

### Families

- Elixir: guards, protocols, protocol implementations, module attributes
- Rust: impl blocks
- Java: applied annotations
- Kotlin: secondary constructors
- PHP: static method call parity proof
- C: typedef persistence

### Validation

- focused parser tests
- end-to-end proof for any feature that should survive graph materialization

## Phase 5: Final Proof And Documentation Lock

### Scope

Prove parity closure and make the docs reflect the completed state.

### Exit criteria

- parity audit shows no remaining feature families marked partial because of
  missing Go-owned graph/query-surface behavior, except intentionally bounded
  non-goals explicitly accepted in docs
- language pages are updated
- support-maturity page and roadmap match the branch truth
- local verification stack passes
- operator docs and runbooks match the actual Go platform

## Suggested Subagent Waves

### Wave A

- operator/runtime contract closure
- SQL/dbt lineage audit and implementation
- TypeScript/TSX graph-surface parity
- Python graph-surface parity

### Wave B

- Terraform/Terragrunt/Kubernetes/ArgoCD parity
- CloudFormation/Kustomize/JSON-family parity
- query-surface parity audit for newly persisted features

### Wave C

- Elixir/Rust/Java/Kotlin/PHP/C long-tail parity
- docs normalization
- final validation sweep

## Source Of Truth

Track completion against:

- `docs/docs/reference/python-to-go-parity.md`
- `docs/docs/reference/parity-closure-matrix.md`
- the affected language pages under `docs/docs/languages/`
- `docs/docs/languages/support-maturity.md`
