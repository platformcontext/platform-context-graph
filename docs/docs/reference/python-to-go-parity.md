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
| `pcg serve start` runtime composition | pass | it starts the HTTP API binary, while MCP is intentionally separate on `pcg mcp start` | keep command behavior and docs aligned exactly |
| API admin route mounting | partial | admin handlers exist in Go but are not fully exposed through the shipped API wiring | either wire the handlers into `pcg-api` or remove the dead surface from code and docs |
| Status endpoint breadth | partial | status surfaces are Go-owned but still narrower than the broader operator contract in some docs | decide the final ingester and run-status surface, then align code and docs |
| Run-scoped index coverage endpoints | partial | some docs describe routes that the current generated OpenAPI does not expose | either implement those endpoints or delete them from the operator contract |
| CLI parity breadth | partial | core CLI ownership is Go, but a few flows are still thinner than the old Python behavior | decide which historical commands are required parity and close them intentionally |

## Feature Parity Status

The table below is the branch-level parity inventory. It separates extraction
parity from persisted graph and query-surface parity.

| Area | Ownership | Parity status | Current truth | Remaining work |
| --- | --- | --- | --- | --- |
| SQL core parsing | Go-owned | mostly complete | schema objects, migrations, embedded SQL hints, `CREATE OR REPLACE FUNCTION` bodies, `CREATE OR REPLACE VIEW`, `CREATE PROCEDURE`, `CREATE MATERIALIZED VIEW`, legacy `EXECUTE PROCEDURE` trigger wiring, and checked-in `ALTER TABLE ... ADD COLUMN ...` column materialization, including bounded multi-clause `ADD COLUMN` normalization, are natively covered in Go | close the remaining procedural SQL and broader DDL edge cases as needed |
| SQL/dbt lineage and data intelligence | Go-owned | pass | dbt manifest, compiled SQL, and analytics JSON families are in Go; row-level aggregates, simple windows, simple qualified macro wrappers, nested safe wrappers, top-level Jinja wrappers around lineage-safe expressions, cast/date_trunc/concat/concat_ws/md5 transforms, fixture-backed wildcard-plus-`coalesce(...)` lineage, and multi-source case/arithmetic lineage now have checked-in Go proof, and `AnalyticsModel` plus `DataAsset` entities now have checked-in content materialization plus normal entity resolve/context proof. The still-unresolved dbt cases are historical Python limitations or bounded non-goals rather than missing Go parity features | broaden real-repo and compose-backed proof, and decide whether richer derived-expression support beyond the Python baseline is worth pursuing as net-new work |
| JavaScript | Go-owned | partial | core JS parsing plus docstring and method-kind metadata extraction/materialization are present, the graph-backed `language-query` path now returns those fields directly from graph rows, `code/search` plus entity-context still enrich matching rows with that metadata, `language-query`, `code/search`, plus entity-context now emit both semantic summaries and a structured `semantic_profile`, JavaScript method-kind rows now get a dedicated `javascript_method` surface kind, entity-context now also emits a first-class `story`, and repository stories now expose semantic coverage through `semantic_overview` | promote docstrings and method-kind metadata into dedicated graph-first modeling beyond the current `language-query` step and the shared query/story surfaces |
| TypeScript | Go-owned | partial | core TS parsing plus decorator/generic metadata preservation are present; type aliases are queryable through Go content-backed APIs, mapped types and conditional types now carry dedicated `type_alias_kind` semantics on the normal Go parser/content/query path, namespace declarations now materialize as `Module` entities with `module_kind=namespace`, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context results now enrich matching rows with that metadata, `language-query`, `code/search`, plus entity-context also emit semantic summaries and a structured `semantic_profile`, entity-context now also emits a first-class `story`, and repository stories now expose semantic coverage through `semantic_overview` | promote those semantics into dedicated graph-first modeling beyond the shared query/story surfaces and close declaration-merging parity |
| TypeScript JSX | Go-owned | partial | core TSX parsing plus JSX tag capture are present; type aliases and component semantics are queryable through Go content-backed APIs, fragment shorthand now survives on function/component entities as `jsx_fragment_shorthand`, `as ComponentType<...>` narrowing now survives on variable entities as `component_type_assertion`, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text and emit both semantic summaries and a structured `semantic_profile` for content-backed component entities, canonical graph writes now persist JSX component usage as first-class `REFERENCES` edges, the query layer still normalizes older graph-backed `CALLS` rows with `call_kind=jsx_component` for compatibility, `code/language-query` now also accepts direct `tsx` requests, entity-context now also emits a first-class `story`, and repository stories now expose semantic coverage through `semantic_overview` | promote component/reference semantics into full graph-first modeling beyond the current canonical edge + fallback surfaces |
| Python language parsing | Go-owned | partial | core Python parsing plus decorator/async extraction are present; type annotations are queryable through Go content-backed APIs, identifier-assigned lambdas now materialize as function entities with `semantic_kind=lambda`, Python class entities now also preserve `metaclass` metadata and surface content-backed `USES_METACLASS` relationships, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, the graph-backed `language-query` path now projects decorator, async, lambda, and metaclass metadata directly from graph rows, and the shared query/context/story surfaces emit semantic summaries plus a structured `semantic_profile` for Python decorator/async/lambda/metaclass/type-annotation semantics | promote those semantics into dedicated persisted graph modeling beyond the current `language-query` step and materialize first-class metaclass relationships |
| Java | Go-owned | partial | core Java parsing is complete, and applied annotations are now graph-first on the normal Go `code/language-query` surface, fall back to content-backed `Annotation` entities when no graph row is present, and resolve/context/story responses now emit humanized annotation summaries plus an `applied_annotation` semantic profile | promote annotation usage into first-class persisted graph surfaces beyond the graph-first query path |
| Kotlin | Go-owned | partial | core Kotlin parsing is complete, secondary constructor metadata now surfaces through normal Go query/context semantic summaries on function entities, explicit `this.` receiver calls now resolve to canonical same-file `CALLS` edges, primary constructor calls inside function bodies now materialize against class entities, extension receivers now stay attached to function metadata, obvious local dotted receiver calls now infer receiver type strongly enough to materialize canonical edges, typed local infix calls now materialize canonical edges too, explicit typed property and constructor-injected property chains plus local alias and dotted property alias chains now materialize canonical edges too, chained property receivers such as `session.service.info()` and safe-call receiver chains such as `session?.service?.info()` now also materialize canonical edges, and reducer proof now covers safe repo-unique cross-file bare-name call materialization for Kotlin `function_calls` | broader receiver/type inference beyond explicit typed declarations, property chains, dotted property aliases, safe-call chains, and simple alias chains is still partial, then continue graph/story promotion plus broader public call-graph/query proof |
| PHP | Go-owned | partial | core PHP parsing is complete, top-level grouped `use` imports now expand natively in the Go parser, same-class typed-property receiver calls now infer receiver type strongly enough to materialize canonical method edges, bounded local aliases from `new` expressions or `$this->property` assignments now also infer receiver type strongly enough to materialize canonical method edges, typed property-chain aliases such as `$this->container->logger` now also infer receiver type strongly enough to materialize canonical method edges, declared method-return-type aliases now also infer receiver type strongly enough to materialize canonical method edges, chained static factory-return receivers such as `Factory::instance()->createService()->info()` and nullsafe receiver chains such as `$session?->service?->info()` now also infer receiver type strongly enough to materialize canonical method edges, and the comprehensive PHP fixture path now proves a dedicated static-call case end to end | broaden object-call inference beyond obvious same-class typed properties, property chains, bounded local aliases, declared method-return-type aliases, chained static factory-return receivers, and nullsafe receiver chains |
| C | Go-owned | partial | core C parsing is complete; typedefs now prefer the graph-first normal `code/language-query` path, fall back to content when the graph is empty, and still carry semantic summaries in normal query/context responses | materialize typedefs as full graph entities and relationships end to end |
| Rust | Go-owned | partial | core Rust parsing is complete, bounded lifetime metadata now survives on Rust function and impl signatures, impl blocks now persist as `ImplBlock` content entities, the normal Go `code/language-query`, entity-context, and `code/relationships` surfaces now expose impl ownership through exact `impl_context` matching, `code/language-query` now tries the graph path before falling back to content for impl blocks, impl-block rows now keep `kind`/`trait`/`target`/`semantic_summary` metadata on the normal query path, canonical call materialization now honors exact `impl_context`-qualified Rust methods, and reducer proof covers safe repo-unique cross-file bare-name call materialization for Rust `function_calls` | persist explicit impl-block graph semantics and relationships end to end, then add broader public call-graph/query proof |
| Elixir | Go-owned | partial | core Elixir parsing is complete, `defprotocol` now materializes as a first-class `Protocol` content entity on the normal Go parser/content/query path, `defimpl` now materializes as a first-class `ProtocolImplementation` content entity on the same normal Go content/query path, and module/function semantic kinds now surface through normal Go query/context semantic summaries, structured `semantic_profile` payloads, and repository-story semantic counts on `Module`, `Protocol`, `ProtocolImplementation`, and `Function` entities; the normal Go query path can also resolve `guard` and `module_attribute` as semantic aliases over flattened `Function` and `Variable` entities | persist guards, protocols, protocol implementations, and module attributes as first-class graph semantics rather than generic metadata |
| Kubernetes | Go-owned | pass | YAML resource parsing is complete, labels/container images/backend refs are preserved, resource identity is normalized into a stable `namespace/kind/name` string, and the Python-era same-name/same-namespace `Service -> Deployment` `SELECTS` heuristic now survives on the Go-owned content/query path | real selector and `matchLabels` resolution was not present in Python either, so it remains out of scope for parity |
| ArgoCD | Go-owned | pass | Applications and ApplicationSets parse in Go; sync policy and ApplicationSet generator wrappers are normalized; generator discovery inputs are now preserved separately from template deploy sources; discovery, deploy-source, and destination-platform evidence materialize in Go; the normal entity resolve/context fallback now surfaces that chain through semantic summaries plus synthesized `DISCOVERS_CONFIG_IN`, `DEPLOYS_FROM`, and `RUNS_ON` relationships; and the Go-owned `trace_deployment_chain` MCP/API path now returns story-first deployment traces with `deployment_overview`, `deployment_sources`, `cloud_resources`, `deployment_facts`, `deployment_fact_summary`, and concrete ArgoCD controller entities in `controller_overview.entities` | keep the current evidence chain validated; Helm-specific source parameters and custom health checks remain bounded non-goals because Python did not model them either |
| CloudFormation | Go-owned | pass | YAML and JSON detection are native Go; both formats now persist `file_format`, cross-stack import/export buckets, first-class condition definitions, evaluated condition results when expressions are template-local, and nested-stack `template_url` metadata; nested `AWS::CloudFormation::Stack` resources now surface that template URL on the Go entity-context path as a synthesized `DEPLOYS_FROM` relationship and resolve obvious repo-local nested-stack targets without losing the raw URL when no local match exists | broaden compose-backed and real-repo proof in the final validation sweep |
| Kustomize | Go-owned | pass | overlays, resources, base references, and inline patch targets parse in Go; base references stay first-class as a sorted list; typed Kustomize evidence for resources vs Helm vs images materializes in Go; normalized `resource_refs`, `helm_refs`, and `image_refs` now persist on the parser payload; and both the historical patch-link heuristic plus typed deploy-source relationships now survive on the Go-owned entity-context/query path | keep the current parser/query coverage validated; `components` breakout and inline patch-body traversal remain bounded non-goals rather than parity blockers |
| Terraform | Go-owned | complete | HCL parser and provider schema support are Go-owned, Go now exceeds the old Python baseline by materializing first-class `terraform {}` block metadata, resource rows now retain raw `count`/`for_each` expressions, and the Postgres ingestion boundary now persists schema-driven Terraform provider evidence into `relationship_evidence_facts` before projector work is enqueued | none for Python-era parity; `count`/`for_each` expansion and `dynamic` traversal remain optional net-new follow-on work |
| Terragrunt | Go-owned | complete | core Terragrunt parsing is complete, dependency/local/input semantics are queryable through Go content entities, and `terraform.source` now also materializes through the normal `TerraformModule` surface | none; historical module-source semantics are now restored |
| Generic JSON | Go-owned | intentionally partial | arbitrary JSON stays quiet to avoid graph noise | confirm whether Python-era behavior needs any targeted JSON families promoted |

## Documented Gap Inventory

These are the currently documented partial or unsupported graph-surface
capabilities in the checked-in language pages:

- TypeScript: dedicated graph-first modeling for decorators, generics, mapped types, conditional types, and namespace modules, with graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context metadata enrichment now in place, `language-query`, `code/search`, and entity-context semantic summaries plus structured `semantic_profile` output now in place for matching graph-backed entities, entity-context `story` now in place, repository-story semantic aggregation now in place, plus content-backed entity resolve/context and `code/search` fallback coverage for type aliases; declaration merging is still partial
- TypeScript JSX: dedicated graph-first modeling for JSX component/reference semantics, with type aliases and component semantics now available through both content-backed query APIs and content-backed entity resolve/context, direct `tsx` support on `code/language-query`, content-backed `code/search` fallback coverage, semantic-summary plus `semantic_profile` fallback for content-backed components, fragment shorthand and `as ComponentType<...>` narrowing now promoted into semantic summaries and repository-story aggregation, entity-context `story` now in place, repository-story semantic aggregation now in place, and synthesized JSX component-reference edges on the normal `code/relationships` fallback path
- Python: dedicated persisted graph modeling for decorators, async functions, lambda ownership, and metaclass ownership, with graph-backed `language-query` now projecting those semantics directly from graph rows, shared `code/search` / `entities/resolve` / entity-context enrichment still in place, semantic-summary plus structured `semantic_profile` output now in place, entity-context `story` now in place, repository-story semantic aggregation now in place, plus content-backed entity resolve/context and `code/search` fallback coverage for type annotations, `semantic_kind=lambda`, and content-backed `USES_METACLASS` relationships for Python classes that declare a metaclass
- JavaScript: dedicated graph-first modeling beyond the now-enriched `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context metadata/semantic-summary/`semantic_profile` surfaces, with JavaScript method-kind rows now also getting a dedicated `javascript_method` surface kind, entity-context `story`, and repository-story semantic aggregation now also in place
- Java: applied annotations are graph-first on the normal Go `code/language-query` surface, fall back to content-backed `Annotation` entities when the graph is empty, and normal resolve/context/story responses now expose humanized semantic summaries plus an `applied_annotation` semantic profile, but persisted graph promotion is still partial
- Kotlin: secondary constructors now surface through semantic summaries on normal query/context responses, explicit `this.` receiver calls materialize canonically, primary constructor calls inside function bodies now resolve to class entities, constructor-injected property receivers now infer receiver type strongly enough to materialize canonical edges, and both obvious local dotted calls, typed local infix calls, explicit typed property/local alias/dotted property alias chains, chained property receivers, and safe-call receiver chains now infer receiver type strongly enough to materialize canonical edges, but broader receiver/type inference and graph/story promotion are still partial
- PHP: arbitrary receiver-chain and interprocedural object-call inference beyond the currently bounded typed-property, property-chain, local-alias, declared method-return-type, chained static factory-return, and nullsafe receiver proof
- C: typedef graph-first materialization beyond the now-supported graph-first `code/language-query`, entity-resolve/context, and semantic-summary surfaces
- Rust: impl blocks now persist as `ImplBlock` content entities, bounded lifetime metadata now survives on function and impl signatures, the normal Go `code/language-query`, entity-context, and `code/relationships` surfaces expose exact impl ownership, `code/language-query` now tries the graph path before falling back to content for impl blocks, impl-block rows keep `kind`/`trait`/`target`/`semantic_summary` metadata on the normal query path, but graph implementation edges remain partial
- Elixir: guards and module attributes now appear in semantic summaries, structured `semantic_profile` payloads, and repository-story semantic counts on normal query/context responses, the normal Go query path can resolve them through semantic aliases, and `defprotocol` plus `defimpl` now materialize as first-class `Protocol` and `ProtocolImplementation` content entities, but the graph still stores those semantics as generic modules/functions/variables
- Terragrunt: module-source semantics from `terraform.source` are now restored through the normal `TerraformModule` surface
- JSON: generic JSON intentionally remains partial
- SQL/dbt: Python-era feature parity is met, but validation maturity is still narrower than the final desired bar because broader real-repo and compose-backed proof remains to be expanded

The parser-family audit currently groups the remaining work into these high
leverage buckets:

- shared JavaScript family closure for JavaScript, TypeScript, and TSX
- shared YAML/IaC validation sweep for Kubernetes, ArgoCD, CloudFormation, and Kustomize
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
3. Infra normalization validation sweep for Terraform, Terragrunt, Kubernetes,
  ArgoCD, CloudFormation, and Kustomize
4. Long-tail graph-surface parity for Elixir, Rust, Java, Kotlin, PHP, and C
5. Final documentation and validation sweep

## Companion Plan

Use the execution plan in
`docs/superpowers/plans/2026-04-14-go-parity-closure-plan.md` to finish the
remaining parity work in milestone-sized chunks.

For the approval and execution checklist view, use
`docs/docs/reference/parity-closure-matrix.md`.
