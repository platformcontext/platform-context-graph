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
- canonical code-call materialization is now parity-complete end to end through
  collector follow-up emission, reducer materialization, canonical Neo4j edge
  writes, and the public `code/relationships`, `code/call-chain`, and
  decorator-aware `code/dead-code` query surfaces

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
| API admin route mounting | pass | the shipped Go API now exposes the public `/api/v0/admin/*` control surface while the same process also mounts the shared service-local runtime admin probes and status routes | keep OpenAPI, docs, and query wiring aligned with the mounted admin contract |
| Status endpoint breadth | pass | the API runtime now mounts the shared `/healthz`, `/readyz`, `/admin/status`, and `/metrics` surface, while the public query API exposes canonical `/api/v0/status/*` routes plus legacy `GET /api/v0/ingesters*` aliases for ingester status | keep docs, OpenAPI, and tests aligned with the shipped surface |
| Run-scoped index coverage endpoints | bounded | the shipped completeness contract is `GET /api/v0/status/index`, legacy `GET /api/v0/index-status`, and repository-scoped `GET /api/v0/repositories/{repo_id}/coverage`; run-scoped coverage endpoints are intentionally not part of the public OpenAPI contract on this branch | keep that bounded contract explicit instead of reintroducing stale run-scoped claims |
| CLI parity breadth | partial | core CLI ownership is Go, but a few flows are still thinner than the old Python behavior | decide which historical commands are required parity and close them intentionally |

## Feature Parity Status

The table below is the branch-level parity inventory. It separates extraction
parity from persisted graph and query-surface parity.

| Area | Ownership | Parity status | Current truth | Remaining work |
| --- | --- | --- | --- | --- |
| SQL core parsing | Go-owned | pass | schema objects, migrations, embedded SQL hints, `CREATE TABLE IF NOT EXISTS`, `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION` bodies, tagged dollar-quoted procedural bodies with `LANGUAGE` before or after `AS`, `CREATE OR REPLACE VIEW`, `CREATE PROCEDURE`, `CREATE MATERIALIZED VIEW`, legacy `EXECUTE PROCEDURE` trigger wiring, and checked-in `ALTER TABLE ... ADD COLUMN ...` column materialization, including bounded multi-clause `ADD COLUMN` normalization, are natively covered in Go with parser, content, and query fallback proof | none for Python-era parity; broader dialect-specific procedural forms and wider ALTER/DDL mutation normalization remain bounded non-goals that Python did not cover either |
| SQL/dbt lineage and data intelligence | Go-owned | pass | dbt manifest, compiled SQL, and analytics JSON families are in Go; row-level aggregates, simple windows, simple qualified macro wrappers, nested safe wrappers, top-level Jinja wrappers around lineage-safe expressions, cast/date_trunc/concat/concat_ws/md5 transforms, fixture-backed wildcard-plus-`coalesce(...)` lineage, and multi-source case/arithmetic lineage now have checked-in Go proof, and `AnalyticsModel` plus `DataAsset` entities now have checked-in content materialization plus normal entity resolve/context proof. The still-unresolved dbt cases are historical Python limitations or bounded non-goals rather than missing Go parity features | broaden real-repo and compose-backed proof, and decide whether richer derived-expression support beyond the Python baseline is worth pursuing as net-new work |
| JavaScript | Go-owned | pass | core JS parsing plus docstring and method-kind metadata extraction/materialization are present, generator functions carry `semantic_kind=generator`, compile-time constant computed class-member expressions normalize to names, static CommonJS `require()` imports are tracked, the graph-backed `language-query` path returns those fields directly from graph rows, `code/search`, `entities/resolve`, `code/call-chain`, `dead-code`, `code/relationships`, and `code/complexity` preserve graph-backed JavaScript metadata when the row already carries it, `entities/{entity_id}/context` promotes graph-backed JavaScript metadata directly into `metadata`, `semantic_summary`, `semantic_profile`, and `story`, shared query outputs emit both semantic summaries and a structured `semantic_profile`, JavaScript method-kind rows get a dedicated `javascript_method` surface kind, and repository stories expose semantic coverage through `semantic_overview` | no remaining Python-era JavaScript parity gap on the documented graph/query surfaces |
| TypeScript | Go-owned | pass | core TS parsing plus decorator/generic metadata preservation are present; canonical `Function`, `Class`, and `Interface` rows now persist `decorators` and `type_parameters` through the Go projector/reducer/Neo4j path, type aliases now persist as first-class `TypeAlias` graph nodes, mapped types and conditional types now carry dedicated `type_alias_kind` semantics on the normal Go parser/content/query path, namespace declarations now materialize as first-class `Module` graph entities with `module_kind=namespace`, declaration-merging metadata now also persists through that semantic-entity path, the shared graph-backed `language-query` path now also projects namespace and declaration-merging metadata directly from matching graph rows, content-backed entities still participate in normal entity resolve/context, the normal `code/search` fallback still searches entity names as well as source text, graph-backed `language-query`, `code/search`, `dead-code`, `code/relationships`, `code/complexity`, `entities/resolve`, and entity-context results now enrich matching rows with that metadata, `language-query`, `code/search`, plus entity-context also emit semantic summaries and a structured `semantic_profile`, entity-context now also emits a first-class `story`, and repository stories now expose semantic coverage through `semantic_overview` | TypeScript graph parity is complete on the documented surfaces |
| TypeScript JSX | Go-owned | pass | core TSX parsing plus JSX tag capture are present; type aliases now persist as first-class `TypeAlias` graph nodes, component semantics now persist as first-class `Component` graph nodes through the Go projector/reducer/Neo4j path, fragment shorthand survives on function/component entities as `jsx_fragment_shorthand`, `as ComponentType<...>` narrowing plus direct type-annotation forms survive on variable entities as `component_type_assertion`, `React.FC(...)` and namespace-qualified `React.FunctionComponent(...)` assertions also survive on variable entities as `component_type_assertion`, `memo(...)`, `forwardRef(...)`, `lazy(...)`, and parenthesized wrapper calls survive on component entities as `component_wrapper_kind`, the shared graph-backed `language-query` path projects fragment shorthand, component-assertion, and wrapper metadata directly from matching graph rows, content-backed entities still participate in normal entity resolve/context when the graph is empty, the normal `code/search` fallback still searches entity names as well as source text and emits both semantic summaries and a structured `semantic_profile` for matching component entities, canonical graph writes persist JSX component usage as first-class `REFERENCES` edges, the query layer still normalizes older graph-backed `CALLS` rows with `call_kind=jsx_component` for compatibility, `code/language-query` accepts direct `tsx` requests, entity-context emits a first-class `story`, and repository stories expose semantic coverage through `semantic_overview` | no remaining Python-era TSX parity gap on the documented graph/query surfaces |
| Python language parsing | Go-owned | pass | core Python parsing plus decorator/async extraction are present; type annotations are queryable through Go content-backed APIs, function-signature and annotated-assignment type annotations now materialize as first-class `TypeAnnotation` entities, identifier-assigned, attribute-assigned, and anonymous inline lambdas now materialize as function entities with `semantic_kind=lambda`, generator functions now materialize as function entities with `semantic_kind=generator`, Python semantic `Function` entities carrying decorators, async flags, generator semantics, or lambda semantics now also persist through the Go semantic-entity projector/reducer/Neo4j path, Python class entities now also preserve `metaclass` metadata and persist `USES_METACLASS` relationships, Python module docstrings now materialize as first-class `Module` entities, content-backed entities now participate in normal entity resolve/context, the normal `code/search` fallback can now search content-backed entity names as well as source text, content-backed decorator-only, async-only, decorated-async, assignment-annotation, and parameter-annotation rows now have explicit resolve/context proof, and graph-backed `language-query`, `code/search`, `entities/resolve`, `dead-code`, `code/complexity`, plus entity-context/story now project Python semantics directly from graph rows with a first-class `python_semantics` bundle and corrected surface-kind priority | validation sweep only |
| Java | Go-owned | pass | core Java parsing is complete, applied annotations now persist as first-class `Annotation` graph nodes through the Go projector/reducer/Neo4j path, remain graph-first on the normal Go `code/language-query` surface, fall back to content-backed `Annotation` entities when no graph row is present, and resolve/context/story responses emit humanized annotation summaries plus an `applied_annotation` semantic profile | none for Python-era parity |
| Kotlin | Go-owned | partial | core Kotlin parsing is complete, secondary constructor metadata now persists as `constructor_kind` on Function graph rows and surfaces through normal Go query/context semantic summaries and stories, explicit `this.` receiver calls now resolve to canonical same-file `CALLS` edges, primary constructor calls inside function bodies now materialize against class entities, extension receivers now stay attached to function metadata, obvious local dotted receiver calls now infer receiver type strongly enough to materialize canonical edges, typed local infix calls now materialize canonical edges too, explicit typed property, explicit cast assignments such as `val service = any as Service`, direct cast-expression receivers such as `(any as Service).info()`, object receivers such as `AppConfig.isProduction()`, companion-object receivers such as `Person.create()`, flow-sensitive smart-cast receiver branches such as `if (any is Service) any.info()` and `when (value) { is Factory -> value.createService().info() }`, nullable generic receiver flows such as `Box<Service>?`, generic-return hops such as `Box<T>.unwrap(): T`, and constructor-injected property chains plus local alias and dotted property alias chains now materialize canonical edges too, chained property receivers such as `session.service.info()`, safe-call receiver chains such as `session?.service?.info()`, safe-call alias assignments such as `val provider = session?.service`, receiver-preserving scope-function assignments such as `val service = createService().apply { }` or `val service = createService().also { }`, delegated lazy property receivers such as `val service by lazy { createService() }`, same-file function-return aliases including re-aliased local chains such as `val provider = createService(); val active = provider; active.info()`, sibling-file re-aliased local chains with the same package shape, bounded same-file function-return receiver chains such as `factory.createService().info()`, parenthesized cross-file package-aware receiver chains such as `(createFactory().createService()).info()`, and package-aware sibling return lookup across conflicting same-name helper packages now also materialize canonical edges, and reducer proof now covers safe repo-unique cross-file bare-name call materialization for Kotlin `function_calls` | broader receiver/type inference beyond the explicit typed, cast, smart-cast, property, safe-call, object, companion-object, generic-nullable, and bounded function-return cases already proven is still partial, then continue graph/story promotion plus broader public call-graph/query proof |
| PHP | Go-owned | partial | core PHP parsing is complete, top-level grouped `use` imports now expand natively in the Go parser, same-class typed-property receiver calls now infer receiver type strongly enough to materialize canonical method edges, imported class aliases now resolve through the Go parser so `use Foo\Bar as Baz; $baz->info()` materializes canonically, direct `self::emit()` / `static::emit()` calls now materialize as distinct canonical static call sites, imported static alias receiver chains such as `use Demo\Library\Factory as AppFactory; AppFactory::instance()->createService()->info()` now also materialize canonical call edges, same-class and inherited static typed-property receiver chains such as `self::$service->info()`, `parent::$service->info()`, and `static::$service->info()` plus deeper static typed-property chains such as `self::$factory->createService()->info()`, `parent::$factory->createService()->info()`, and `static::$factory->createService()->info()` now also materialize canonical method edges, bounded local aliases from `new` expressions or `$this->property` assignments now also infer receiver type strongly enough to materialize canonical method edges, typed property-chain aliases such as `$this->container->logger` now also infer receiver type strongly enough to materialize canonical method edges, same-file free-function return aliases such as `$service = createService(); $service->info()`, same-file free-function return property-chain aliases such as `createFactory()->logger->info()`, direct same-file free-function return receiver chains such as `createService()->info()`, same-file free-function return call chains such as `createFactory()->createService()->info()`, parenthesized receiver chains such as `($this->factory->createService())->info()`, declared method-return-type aliases now also infer receiver type strongly enough to materialize canonical method edges, method-return property chains such as `$this->factory->createService()->logger` now also infer receiver type strongly enough to materialize canonical method edges, cross-file method-return property-dereference chains with namespaced inferred receiver types such as `Demo\\Logger` now also resolve to the local target method entity, chained static factory-return receivers such as `Factory::instance()->createService()->info()`, nullsafe receiver chains such as `$session?->service?->info()`, and trait-adaptation `as` aliases now materialize both class-level and method-level graph-visible `ALIASES` edges on the reducer/query path, and the comprehensive PHP fixture path now proves dedicated static-call cases end to end | broaden object-call inference beyond the bounded same-file receiver-chain and interprocedural forms already proven; PHP trait aliasing no longer needs a separate method-level parity follow-up |
| C | Go-owned | pass | core C parsing is complete; typedefs now persist as first-class `Typedef` graph nodes through the Go projector/reducer/Neo4j path, prefer the graph-first normal `code/language-query` path, fall back to content when the graph is empty, and still carry semantic summaries in normal query/context responses | none for Python-era parity |
| Rust | Go-owned | pass | core Rust parsing is complete, bounded lifetime metadata now survives on Rust function and impl signatures, impl blocks now persist as `ImplBlock` graph nodes, the normal Go `code/language-query`, `code/call-chain`, entity-context, and `code/relationships` surfaces expose exact impl ownership through `impl_context` matching and graph-first `CONTAINS` edges, impl-block rows keep `kind`/`trait`/`target`/`semantic_summary` metadata on the normal query path, and canonical call materialization honors exact `impl_context`-qualified Rust methods | broader lifetime-aware graph semantics remain bounded, but Python-era impl ownership/query parity is closed |
| Elixir | Go-owned | pass | core Elixir parsing is complete, `guard`, `module_attribute`, `defprotocol`, and `defimpl` now all persist as first-class graph-backed semantics through the Go semantic-entity materialization path, the shared graph-backed `language-query` path serves them directly without content fallback, and normal query/context/story responses emit semantic summaries, structured `semantic_profile` payloads, and repository-story semantic counts for those entities | current remaining Elixir limitations are parser-shape limitations already documented in the language page, not Python-era graph-parity gaps |
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
- Kotlin: secondary constructors now surface through semantic summaries and stories on normal query/context responses, explicit `this.` receiver calls materialize canonically, primary constructor calls inside function bodies now resolve to class entities, constructor-injected property receivers now infer receiver type strongly enough to materialize canonical edges, explicit cast assignments such as `val service = any as Service` and direct cast-expression receivers such as `(any as Service).info()` now also infer receiver type strongly enough to materialize canonical edges, object receivers such as `AppConfig.isProduction()`, companion-object receivers such as `Person.create()`, flow-sensitive smart-cast receiver branches such as `if (any is Service) any.info()` and `when (value) { is Factory -> value.createService().info() }` now also infer receiver type strongly enough to materialize canonical edges, nullable generic receiver flows such as `Box<Service>?`, generic-return hops such as `Box<T>.unwrap(): T`, safe-call alias assignments now also infer receiver type strongly enough to materialize canonical edges, receiver-preserving scope-function assignments such as `val service = createService().apply { }` and `val service = createService().also { }` now also infer receiver type strongly enough to materialize canonical edges, delegated lazy property receivers such as `val service by lazy { createService() }` now also infer receiver type strongly enough to materialize canonical edges, same-file function-return aliases including re-aliased local chains and sibling-file re-aliased local chains now infer receiver type strongly enough to materialize canonical edges, package-aware sibling return lookup now reaches deeper package-root directories, and both obvious local dotted calls, typed local infix calls, explicit typed property/local alias/dotted property alias chains, chained property receivers, safe-call receiver chains, safe-call alias assignments, delegated lazy property receivers, and branch-local smart-cast receivers now infer receiver type strongly enough to materialize canonical edges, but broader receiver/type inference remains partial
- PHP: direct `self::` / `static::` static calls, same-class and inherited static typed-property receiver chains such as `self::$service->info()`, `parent::$service->info()`, and `static::$service->info()`, deeper static typed-property chains such as `self::$factory->createService()->info()`, `parent::$factory->createService()->info()`, and `static::$factory->createService()->info()`, imported static alias receiver chains such as `use Demo\Library\Factory as AppFactory; AppFactory::instance()->createService()->info()`, and trait-adaptation `as` aliases that now materialize both class-level and method-level `ALIASES` edges all materialize canonically alongside the already-proven imported class aliases, typed-property chains, return-type aliases, chained static factory returns, and nullsafe receiver chains, but the broader object-call surface is still partial
- PHP: arbitrary receiver-chain and interprocedural object-call inference beyond the currently bounded typed-property, static typed-property, deeper static typed-property, imported class alias, property-chain, local-alias, declared method-return-type, method-return property-chain, namespaced cross-file method-return property-dereference, chained static factory-return, parenthesized receiver, and nullsafe receiver proof
- Rust: graph-native impl ownership is now first-class, bounded lifetime metadata survives on function and impl signatures, the normal Go `code/language-query`, entity-context, `code/call-chain`, and `code/relationships` surfaces expose exact impl ownership, `code/language-query` tries the graph path before falling back to content for impl blocks, and impl-block rows keep `kind`/`trait`/`target`/`semantic_summary` metadata on the normal query path; the remaining limitation is bounded lifetime semantics rather than Python-era parity debt
- Elixir: guards and module attributes now appear in semantic summaries, structured `semantic_profile` payloads, and repository-story semantic counts on normal query/context responses, the normal Go query path can resolve them through semantic aliases, and `defprotocol` plus `defimpl` now persist as first-class `Protocol` and `ProtocolImplementation` graph nodes; the remaining limitations are parser-shape constraints already documented in the language page rather than Python-era parity debt
- Terragrunt: module-source semantics from `terraform.source` are now restored through the normal `TerraformModule` surface
- JSON: generic JSON intentionally remains partial
- SQL/dbt: Python-era feature parity is met, but validation maturity is still narrower than the final desired bar because broader real-repo and compose-backed proof remains to be expanded

The parser-family audit currently groups the remaining work into these high
leverage buckets:

- shared YAML/IaC validation sweep for Kubernetes, ArgoCD, CloudFormation, and Kustomize
- shared HCL closure for Terraform and Terragrunt
- single-family graph promotions for Kotlin and PHP

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
2. TSX, JavaScript, and Python graph-surface parity
3. Infra normalization validation sweep for Terraform, Terragrunt, Kubernetes,
  ArgoCD, CloudFormation, and Kustomize
4. Long-tail graph-surface parity for Kotlin and PHP
5. Final documentation and validation sweep

## Companion Plan

Use the execution plan in
`docs/superpowers/plans/2026-04-14-go-parity-closure-plan.md` to finish the
remaining parity work in milestone-sized chunks.

For the approval and execution checklist view, use
`docs/docs/reference/parity-closure-matrix.md`.
