# Python-To-Go Parity Audit

This page is the source of truth for parity closure on the
`codex/go-data-plane-architecture` branch.

Use it to answer two different questions clearly:

1. Is the normal platform runtime Go-owned?
2. Are all Python-era features already matched feature for feature?

Those are not the same bar.

## Executive Summary

The runtime migration is complete:

- no runtime `.py` files remain outside `tests/fixtures/`
- no `src/` service tree remains
- deployed and local long-running services are Go-owned
- Dockerfile, Compose, Helm, admin/status, and recovery paths are Go-owned
- Terraform provider schema loading is Go-owned through
  `go/internal/terraformschema/`

Feature parity is not yet complete.

The current repo still documents multiple parser or graph-surface capabilities
as `partial` or `unsupported`, plus a handful of non-parser operator-surface
gaps where the Go implementation is present but still narrower than the Python
platform contract.

That means the branch is structurally migrated off Python, but it is not yet
honest to call the rewrite feature-for-feature parity complete.

## Verification Evidence

The current branch truth is backed by these checks:

- `rg --files . -g '*.py' | rg -v '^tests/fixtures/'` returns no runtime Python files
- `rg --files . | rg '^src/'` returns no Python service tree
- strict docs build passes
- targeted Go parser, relationship, and Terraform schema tests pass
- `golangci-lint` passes for the parser, relationship, and Terraform schema packages

## Structural Migration Status

| Area | Status | Evidence | Remaining parity risk |
| --- | --- | --- | --- |
| Runtime services | complete | `go/cmd/`, `docs/docs/deployment/service-runtimes.md`, Compose and Helm assets | feature parity only |
| CLI and admin flows | complete | `go/cmd/pcg/*`, `go/internal/query/*`, `go/internal/runtime/*` | feature parity only |
| Recovery and refinalize | complete | `go/internal/recovery/*`, `go/internal/runtime/recovery_handler.go`, `go/internal/storage/postgres/recovery.go` | validation breadth |
| Deployment assets | complete | `Dockerfile`, `docker-compose.yaml`, `deploy/helm/platform-context-graph/*` | validation breadth |
| Telemetry and status | complete | `go/internal/telemetry/*`, `go/internal/runtime/*`, telemetry docs | keep docs aligned |
| Terraform provider schema ownership | complete | `go/internal/terraformschema/*`, `go/internal/relationships/*` | schema refresh cadence |
| Python runtime ownership | complete | no runtime `.py` files outside fixtures | none |

## Non-Parser Platform Parity Gaps

These are the currently known branch-level gaps outside parser family work.

| Area | Status | Current truth | Remaining work |
| --- | --- | --- | --- |
| `pcg serve start` runtime composition | partial | today it starts the API binary, while MCP is a separate binary | either mount both services under the advertised contract or rename and document the command as API-only |
| API admin route mounting | partial | admin handlers exist in Go but are not fully exposed through the shipped API wiring | either wire the handlers into `pcg-api` or remove the dead surface from code and docs |
| Status endpoint breadth | partial | status surfaces are Go-owned but still narrower than the broader operator contract in some docs | decide the final ingester and run-status surface, then align code and docs |
| Run-scoped index coverage endpoints | partial | some docs describe routes that the current generated OpenAPI does not expose | either implement those endpoints or delete them from the operator contract |
| CLI parity breadth | partial | core CLI ownership is Go, but a few flows are still thinner than the old Python behavior | decide which historical commands are required parity and close them intentionally |

## Feature Parity Status

The table below is the branch-level parity inventory. It separates extraction
parity from persisted graph and query-surface parity.

| Area | Ownership | Parity status | Current truth | Remaining work |
| --- | --- | --- | --- | --- |
| SQL core parsing | Go-owned | mostly complete | schema objects, migrations, and embedded SQL hints are native Go | close procedural SQL and DDL edge cases as needed |
| SQL/dbt lineage and data intelligence | Go-owned | partial | dbt manifest, compiled SQL, and analytics JSON families are in Go | resolve macros, templated expressions, unresolved references, window semantics, and multi-input derived expressions |
| JavaScript | Go-owned | partial | core JS parsing is complete | persist or normalize docstrings and fuller method-kind metadata |
| TypeScript | Go-owned | partial | core TS parsing and framework packs are complete | materialize type aliases, decorators, and generics into the graph/query surface |
| TypeScript JSX | Go-owned | partial | core TSX parsing and React/Next evidence are complete | add dedicated JSX component-reference semantics and type-alias persistence |
| Python language parsing | Go-owned | partial | core Python parsing and framework packs are complete | persist decorators, async flags, and type annotations |
| Java | Go-owned | partial | core Java parsing is complete | persist applied annotation usage |
| Kotlin | Go-owned | partial | core Kotlin parsing is complete | persist secondary constructor semantics |
| PHP | Go-owned | partial | core PHP parsing is complete | expand end-to-end proof for static method call graph edges |
| C | Go-owned | partial | core C parsing is complete | materialize typedefs as graph entities |
| Rust | Go-owned | partial | core Rust parsing is complete | persist explicit impl-block graph semantics |
| Elixir | Go-owned | partial | core Elixir parsing is complete | persist guards, protocols, protocol implementations, and module attributes |
| Kubernetes | Go-owned | partial | YAML resource parsing is complete | normalize and persist labels |
| ArgoCD | Go-owned | partial | Applications and ApplicationSets parse in Go | normalize and persist sync policy |
| CloudFormation | Go-owned | partial | YAML and JSON detection are native Go | bring JSON-template fixture and end-to-end proof to YAML parity |
| Kustomize | Go-owned | partial | overlays and resources parse in Go | model base references explicitly |
| Terraform | Go-owned | partial | HCL parser and provider schema support are Go-owned | materialize `terraform {}` block metadata as a first-class graph surface if parity requires it |
| Terragrunt | Go-owned | partial | core Terragrunt parsing is complete | normalize locals and inputs into independently queryable entities |
| Generic JSON | Go-owned | intentionally partial | arbitrary JSON stays quiet to avoid graph noise | confirm whether Python-era behavior needs any targeted JSON families promoted |

## Documented Gap Inventory

These are the currently documented partial or unsupported graph-surface
capabilities in the checked-in language pages:

- TypeScript: type aliases, decorators, generics
- TypeScript JSX: type aliases, JSX component usage
- Python: decorators, async functions, type annotations
- JavaScript: JSDoc comments, method kind metadata
- Java: applied annotations
- Kotlin: secondary constructors
- PHP: static method calls end-to-end proof
- C: typedefs
- Rust: impl blocks
- Elixir: guards, protocols, protocol implementations, module attributes
- Kubernetes: labels
- ArgoCD: sync policy
- CloudFormation: JSON-template parity
- Kustomize: base references
- Terraform: `terraform {}` block metadata
- Terragrunt: locals, inputs
- JSON: generic JSON intentionally remains partial
- SQL/dbt: compiled lineage maturity remains partial even though the runtime is Go-owned

The parser-family audit currently groups the remaining work into these high
leverage buckets:

- shared JavaScript family closure for JavaScript, TypeScript, and TSX
- shared YAML/IaC closure for Kubernetes, ArgoCD, and CloudFormation
- shared HCL closure for Terraform and Terragrunt
- SQL/dbt lineage closure
- single-family graph promotions for Python, Elixir, Rust, Java, Kotlin, PHP,
  and C

## What Counts As Parity Complete

A feature family is parity complete only when all of the following are true:

1. The capability is extracted by the Go parser or Go runtime.
2. The capability is persisted into the graph or content surface when the
   Python version previously exposed it.
3. The capability is queryable through the normal API, MCP, story, or context
   surfaces where the Python version previously surfaced it.
4. Fixture-backed tests exist.
5. Real-repo or compose-backed end-to-end proof exists where the feature is
   expected to survive the full pipeline.
6. The language page no longer marks the feature `partial` or `unsupported`.

If any of those are missing, the feature is not parity complete.

## Recommended Closure Order

1. Fix the remaining non-parser platform gaps that still distort the operator contract
2. SQL/dbt lineage parity
3. TypeScript, TSX, JavaScript, and Python graph-surface parity
4. Infra normalization parity for Terraform, Terragrunt, Kubernetes, ArgoCD,
   CloudFormation, and Kustomize
5. Long-tail graph-surface parity for Elixir, Rust, Java, Kotlin, PHP, and C
6. Final documentation and validation sweep

## Companion Plan

Use the execution plan in
`docs/superpowers/plans/2026-04-14-go-parity-closure-plan.md` to finish the
remaining parity work in milestone-sized chunks.
