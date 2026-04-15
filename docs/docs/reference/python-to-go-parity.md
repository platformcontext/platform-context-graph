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
| SQL core parsing | Go-owned | mostly complete | schema objects, migrations, embedded SQL hints, `CREATE OR REPLACE FUNCTION` bodies, and legacy `EXECUTE PROCEDURE` trigger wiring are natively covered in Go | close the remaining procedural SQL and richer DDL edge cases as needed |
| SQL/dbt lineage and data intelligence | Go-owned | pass | dbt manifest, compiled SQL, and analytics JSON families are in Go; row-level aggregates, simple windows, simple qualified macro wrappers, nested safe wrappers, top-level Jinja wrappers around lineage-safe expressions, cast/date_trunc/concat/concat_ws/md5 transforms, fixture-backed wildcard-plus-`coalesce(...)` lineage, and multi-source case/arithmetic lineage now have checked-in Go proof, and `AnalyticsModel` plus `DataAsset` entities now have checked-in content materialization plus normal entity resolve/context proof. The still-unresolved dbt cases are historical Python limitations or bounded non-goals rather than missing Go parity features | broaden real-repo and compose-backed proof, and decide whether richer derived-expression support beyond the Python baseline is worth pursuing as net-new work |
| JavaScript | Go-owned | partial | core JS parsing plus docstring and method-kind metadata extraction/materialization are present, graph-backed query surfaces enrich matching rows with that metadata, and `language-query`, `code/search`, plus entity-context now emit both semantic summaries and a structured `semantic_profile` for matching JavaScript entities | promote docstrings and method-kind metadata into fuller graph-first and higher-level story surfaces beyond the current shared query/context responses |
| TypeScript | Go-owned | partial | core TS parsing plus decorator/generic metadata preservation are present; type aliases are queryable through Go content-backed APIs, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, and graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context results now enrich matching rows with that metadata while `language-query`, `code/search`, plus entity-context also emit semantic summaries and a structured `semantic_profile` for matching graph-backed entities | promote decorators and generics into fuller graph-first and higher-level story/context surfaces |
| TypeScript JSX | Go-owned | partial | core TSX parsing plus JSX tag capture are present; type aliases and component semantics are queryable through Go content-backed APIs, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text and emit both semantic summaries and a structured `semantic_profile` for content-backed component entities, and normal `code/relationships` now synthesizes JSX component `REFERENCES` edges for content-backed entities | promote component/reference semantics into first-class graph/story surfaces beyond the content-backed fallback and close the remaining normal-path alias/story gaps |
| Python language parsing | Go-owned | partial | core Python parsing plus decorator/async extraction are present; type annotations are queryable through Go content-backed APIs, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, graph-backed query surfaces enrich matching rows with that metadata, and `language-query`, `code/search`, plus entity-context now emit semantic summaries and a structured `semantic_profile` for Python decorator/async/type-annotation semantics | promote decorators and async flags into fuller graph-first and higher-level story surfaces |
| Java | Go-owned | partial | core Java parsing is complete, and applied annotations are now queryable through the normal Go `code/language-query` surface as content-backed `Annotation` entities | promote annotation usage into first-class graph/story surfaces beyond the content-backed query path |
| Kotlin | Go-owned | partial | core Kotlin parsing is complete, secondary constructor metadata now surfaces through normal Go query/context semantic summaries on function entities, explicit `this.` receiver calls now resolve to canonical same-file `CALLS` edges, and reducer proof now covers safe repo-unique cross-file bare-name call materialization for Kotlin `function_calls` | persist broader receiver/type inference and constructor semantics as first-class graph/story behavior beyond metadata enrichment, then add broader public call-graph/query proof |
| PHP | Go-owned | partial | core PHP parsing is complete | expand end-to-end proof for static method call graph edges |
| C | Go-owned | partial | core C parsing is complete; typedefs are queryable through the Go content-backed `code/language-query` surface and now carry semantic summaries in normal query/context responses | materialize typedefs as full graph entities and relationships end to end |
| Rust | Go-owned | partial | core Rust parsing is complete, and impl blocks now persist as `ImplBlock` content entities that the normal Go `code/language-query` surface can return; normal entity resolve/context fallbacks now surface semantic summaries too, canonical call materialization now honors exact `impl_context`-qualified Rust methods, and reducer proof now covers safe repo-unique cross-file bare-name call materialization for Rust `function_calls` | persist explicit impl-block graph semantics and relationships end to end, then add broader public call-graph/query proof |
| Elixir | Go-owned | partial | core Elixir parsing is complete, and module/function semantic kinds now surface through normal Go query/context semantic summaries on `Module` and `Function` entities | persist guards, protocols, protocol implementations, and module attributes as first-class graph semantics rather than generic metadata |
| Kubernetes | Go-owned | partial | YAML resource parsing is complete, labels/container images/backend refs are preserved, and resource identity is now normalized into a stable `namespace/kind/name` string | port the historical Python `Service -> Deployment` `SELECTS` heuristic; real selector and `matchLabels` resolution was not present in Python either |
| ArgoCD | Go-owned | partial | Applications and ApplicationSets parse in Go; sync policy and ApplicationSet generator wrappers are normalized; discovery, deploy-source, and destination-platform evidence now materialize in Go | promote the full Application/ApplicationSet evidence chain through the final graph/query surfaces |
| CloudFormation | Go-owned | partial | YAML and JSON detection are native Go; JSON CloudFormation rows now persist `file_format` and share the same parser path as YAML | nested stack references and condition evaluation remain partial |
| Kustomize | Go-owned | partial | overlays, resources, base references, and inline patch targets parse in Go; base references stay first-class as a sorted list; and typed Kustomize evidence for resources vs Helm vs images now materializes in Go | promote the old patch-link heuristic and the typed evidence through the final graph/query surfaces |
| Terraform | Go-owned | complete | HCL parser and provider schema support are Go-owned, and Go now exceeds the old Python baseline by materializing first-class `terraform {}` block metadata | none for Python-era parity; `count`/`for_each` expansion and `dynamic` traversal remain optional net-new follow-on work |
| Terragrunt | Go-owned | complete | core Terragrunt parsing is complete, dependency/local/input semantics are queryable through Go content entities, and `terraform.source` now also materializes through the normal `TerraformModule` surface | none; historical module-source semantics are now restored |
| Generic JSON | Go-owned | intentionally partial | arbitrary JSON stays quiet to avoid graph noise | confirm whether Python-era behavior needs any targeted JSON families promoted |

## Documented Gap Inventory

These are the currently documented partial or unsupported graph-surface
capabilities in the checked-in language pages:

- TypeScript: graph/story/context surfacing for decorators and generics, with graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context metadata enrichment now in place, `language-query`, `code/search`, and entity-context semantic summaries plus structured `semantic_profile` output now in place for matching graph-backed entities, plus content-backed entity resolve/context and `code/search` fallback coverage for type aliases
- TypeScript JSX: graph/story/context surfacing for JSX component/reference semantics, with type aliases and component semantics now available through both content-backed query APIs and content-backed entity resolve/context, plus content-backed `code/search` fallback coverage, semantic-summary plus `semantic_profile` fallback for content-backed components, and synthesized JSX component-reference edges on the normal `code/relationships` fallback path
- Python: graph/story/context surfacing for decorators and async functions, with graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context metadata enrichment now in place, `language-query`, `code/search`, and entity-context semantic summaries plus structured `semantic_profile` output now in place, plus content-backed entity resolve/context and `code/search` fallback coverage for type annotations
- JavaScript: graph/story/context promotion beyond the now-enriched `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context metadata/semantic-summary/`semantic_profile` surfaces
- Java: applied annotations are queryable through content-backed `Annotation` entities, but graph/story promotion is still partial
- Kotlin: secondary constructors now surface through semantic summaries on normal query/context responses, and explicit `this.` receiver calls now materialize canonically, but broader receiver/type inference and graph/story promotion are still partial
- PHP: static method calls end-to-end proof
- C: typedef graph-first materialization beyond the now-supported content-backed `code/language-query` plus semantic-summary surface
- Rust: impl blocks now persist as `ImplBlock` content entities and are queryable through `code/language-query`, plus normal entity resolve/context fallbacks now surface semantic summaries and exact `impl_context`-qualified Rust method calls now materialize canonically, but graph implementation edges remain partial
- Elixir: guards, protocols, protocol implementations, and module attributes now appear in semantic summaries on normal query/context responses, but the graph still stores them as generic modules/functions/variables
- Kubernetes: historical `Service -> Deployment` `SELECTS` heuristic on the relationship side
- ArgoCD: destination-cluster/runtime-platform leg of the historical ApplicationSet evidence chain
- CloudFormation: nested stack references and condition evaluation
- Kustomize: historical patch-link heuristic and final graph/query promotion of the typed evidence
- Terragrunt: module-source semantics from `terraform.source` are now restored through the normal `TerraformModule` surface
- JSON: generic JSON intentionally remains partial
- SQL/dbt: Python-era feature parity is met, but validation maturity is still narrower than the final desired bar because broader real-repo and compose-backed proof remains to be expanded

The parser-family audit currently groups the remaining work into these high
leverage buckets:

- shared JavaScript family closure for JavaScript, TypeScript, and TSX
- shared YAML/IaC closure for Kubernetes, ArgoCD, and CloudFormation
- shared HCL closure for Terraform and Terragrunt
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
2. TypeScript, TSX, JavaScript, and Python graph-surface parity
3. Infra normalization parity for Terraform, Terragrunt, Kubernetes, ArgoCD,
  CloudFormation, and Kustomize
4. Long-tail graph-surface parity for Elixir, Rust, Java, Kotlin, PHP, and C
5. Final documentation and validation sweep

## Companion Plan

Use the execution plan in
`docs/superpowers/plans/2026-04-14-go-parity-closure-plan.md` to finish the
remaining parity work in milestone-sized chunks.

For the approval and execution checklist view, use
`docs/docs/reference/parity-closure-matrix.md`.
