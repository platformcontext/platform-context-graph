# Parity Closure Matrix

This page records the current code-backed truth of the Go platform.

A row is only marked `Closed` when the behavior is implemented in Go and backed
by direct code inspection plus targeted tests or validation on this branch.

Use this page to answer:

- what is already closed in Go
- what is only partially closed
- what still needs targeted closure work before the platform can be called fully closed

## Status Legend

| Status | Meaning |
| --- | --- |
| `Closed` | Implemented in Go and directly validated from code plus focused tests |
| `Partial` | Implemented in part, or documented broadly but not fully re-audited end to end |
| `Open` | Still needs targeted implementation or full proof before claiming parity |

## Current Matrix

| Area | Status | Current truth | Primary evidence | What still needs closure |
| --- | --- | --- | --- | --- |
| Long-running runtimes | `Closed` | API, MCP, ingester, reducer, and bootstrap runtime shapes are implemented in the checked-in services | `go/cmd/api`, `go/cmd/mcp-server`, `go/cmd/ingester`, `go/cmd/reducer`, `go/cmd/bootstrap-index`; runtime docs and local testing runbook | Keep deployment docs aligned as runtime wiring evolves |
| Shared runtime admin contract | `Closed` | `/healthz`, `/readyz`, `/admin/status`, and optional `/metrics` are mounted through shared Go runtime packages | `go/internal/runtime/*`, `go/internal/status/*`, `docs/docs/reference/runtime-admin-api.md` | Continue using the shared contract for new services instead of bespoke probes |
| Structured Go telemetry | `Closed` | Go runtimes emit JSON logs plus OTEL metrics/traces through shared telemetry packages | `go/internal/runtime/observability.go`, `go/internal/telemetry` references in docs and tests | Keep field names stable for operator tooling |
| Terraform provider-schema packaging | `Closed` | Provider schemas are packaged in-repo and loaded from `go/internal/terraformschema/schemas/*.json.gz` | `go/internal/terraformschema/*`, provider docs under `docs/docs/guides/terraform-providers/` | Broader provider coverage can expand later without changing runtime ownership |
| Projector canonical readiness publication | `Closed` | Projector publishes `canonical_nodes_committed` after canonical node writes succeed | `go/internal/projector/runtime.go`, `go/internal/projector/runtime_test.go::TestRuntimeProjectPublishesCanonicalNodesCommittedAfterCanonicalWrite` | None in this slice beyond broader end-to-end corpus proof |
| Reducer semantic readiness publication | `Closed` | Semantic-entity materialization publishes `semantic_nodes_committed` after semantic node writes succeed | `go/internal/reducer/semantic_entity_materialization.go`, `go/internal/reducer/semantic_entity_materialization_test.go::TestSemanticEntityMaterializationPublishesSemanticNodesCommitted` | None in this slice beyond broader end-to-end corpus proof |
| Durable phase-state storage | `Closed` | Bounded graph-readiness state is stored in Postgres `graph_projection_phase_state` and included in bootstrap schema order | `go/internal/storage/postgres/graph_projection_phase_state.go`, `go/internal/storage/postgres/graph_projection_phase_state_test.go`, `schema/data-plane/postgres/012_graph_projection_phase_state.sql`, `go/internal/storage/postgres/schema_test.go` | None for this slice |
| Shared edge readiness gating | `Closed` | Shared edge domains wait on semantic readiness before writing when they require semantic node presence | `go/internal/reducer/shared_projection.go`, `shared_projection_worker.go`, `code_call_projection_runner.go`, related tests | End-to-end fixture proof across larger corpora |
| Code calls / SQL / inheritance edge domains | `Closed` | These domains are explicitly gated by semantic readiness in reducer flow | `domainRequiresSemanticNodeReadiness` and related tests in `go/internal/reducer` | Keep docs aligned if more domains join the gating set |
| Relationship verb contract | `Closed` | Public docs define the canonical resolver-owned verb set, and Go tests now pin that vocabulary exactly while keeping runtime topology edges on the read side where documented | `docs/docs/reference/relationship-mapping.md`, `go/internal/relationships/models_test.go`, `go/internal/query/repository_context_relationship_overview_test.go` | Keep broader family audits aligned, but the verb-contract boundary itself is now proven |
| GitHub Actions relationship evidence | `Partial` | Go relationship/query code clearly contains GitHub Actions evidence extraction and read-path shaping | `go/internal/relationships/github_actions_evidence.go`, `go/internal/query/content_relationships_github_actions.go`, related tests | Final end-to-end proof against local real-world workflow repos |
| Jenkins / Ansible controller-driven evidence | `Partial` | Go relationship layer includes Jenkins and Ansible evidence extraction and tests | `go/internal/relationships/jenkins_evidence.go`, `ansible_evidence.go`, `ansible_jenkins_fixture_test.go` | Final corpus validation against local repos and query surfaces |
| Docker / Compose relationship evidence | `Partial` | Go relationship layer includes Dockerfile and Docker Compose evidence extraction | `go/internal/relationships/dockerfile_evidence.go`, `docker_compose_evidence.go`, related tests | Final query-surface validation and mixed-repo corpus proof |
| Terraform / Terragrunt helper-path relationship coverage | `Partial` | Public docs describe broad helper-built path-expression support; code clearly includes Terraform schema and relationship extraction, but the full documented helper matrix was not re-audited in this pass | `go/internal/relationships/terraform_schema.go`, `terragrunt_helper_evidence.go`, `go/internal/query/repository_*`, `docs/docs/reference/relationship-mapping.md` | Targeted parity audit against local Terraform/Terragrunt repos, especially helper-built and module-source cases |
| Public docs truth for runtime/readiness flow | `Closed` | Public docs now describe projector/reducer phase readiness as implemented in Go instead of implying hidden coupling | this page plus `service-runtimes.md`, `service-workflows.md`, `relationship-mapping.md`, `telemetry/index.md` | Keep docs current as code changes land |
| Repo-wide docs truth for every language and feature page | `Partial` | Major public runtime/docs cleanup is already landed, but the full `docs/docs` tree still needs a systematic line-by-line truth sweep against code | current public docs plus targeted scans | Continue doc audit by feature family until every public claim is evidence-backed |

## Audited Language Families

| Family | Status | Current truth | Primary evidence | What still needs closure |
| --- | --- | --- | --- | --- |
| Go | `Closed` | The documented Go parser surface is supported end to end; only bounded parser nuances remain on the page. | `docs/docs/languages/go.md`, `go/internal/parser/engine_test.go`, `go/internal/parser/go_embedded_sql_test.go`, `go/internal/query/*go*` | Keep the small limitation note honest, but this is not a parity blocker. |
| Python | `Closed` | The documented Python surface is supported end to end on the Go path, including graph-backed query promotion and story surfaces. | `docs/docs/languages/python.md`, `go/internal/parser/engine_python_semantics_test.go`, `go/internal/query/python_semantics_promotion_test.go` | Keep broader corpus validation moving, but no page-level parser/query gap remains. |
| TypeScript | `Closed` | The documented TypeScript surface is supported end to end, including graph-backed metadata and semantic bundles. | `docs/docs/languages/typescript.md`, `go/internal/parser/engine_typescript_advanced_semantics_test.go`, `go/internal/query/typescript_graph_metadata_test.go` | Future whole-program inference is enhancement work, not current parity closure. |
| Kotlin | `Closed` | The documented Kotlin receiver, chaining, and constructor surfaces are supported end to end. | `docs/docs/languages/kotlin.md`, `go/internal/parser/engine_kotlin_*`, `go/internal/query/code_relationships_graph_kotlin_*` | Broader whole-program inference remains future work. |
| Kustomize | `Closed` | The documented Kustomize overlay, patch, and typed deploy-source surfaces are supported end to end. | `docs/docs/languages/kustomize.md`, `go/internal/parser/engine_yaml_semantics_test.go`, `go/internal/query/content_relationships_kustomize_*` | `components`/`configurations` and inline patch bodies remain bounded non-goals. |
| ArgoCD | `Closed` | The documented ArgoCD application, ApplicationSet, fallback, and deployment-trace surfaces are supported end to end. | `docs/docs/languages/argocd.md`, `go/internal/parser/engine_yaml_semantics_test.go`, `go/internal/query/content_relationships_argocd_*`, `go/internal/query/impact_trace_deployment_argocd_test.go` | Helm/plugin-specific generator details and `ignoreDifferences`/custom health checks remain bounded non-goals. |
| JavaScript | `Partial` | The documented JavaScript surface is supported, but some runtime-dependent behavior remains bounded. | `docs/docs/languages/javascript.md`, `go/internal/parser/engine_javascript_semantics_test.go`, `go/internal/query/language_query_graph_first_test.go` | Computed expressions and dynamic `require()` targets stay intentionally bounded. |
| PHP | `Partial` | The documented PHP surface is supported, but fully dynamic dispatch remains bounded. | `docs/docs/languages/php.md`, `go/internal/parser/php_language_parent_static_test.go`, `go/internal/query/code_relationships_graph_kotlin_php_test.go` | Reflection-heavy call sites and arbitrary alias flow remain future work. |
| Java | `Partial` | The documented Java surface is supported, but generic and lambda modeling is still bounded. | `docs/docs/languages/java.md`, `go/internal/parser/engine_managed_oo_test.go`, `go/internal/query/language_query_metadata_test.go` | Generic bounds/wildcards, anonymous inner classes, and lambdas remain incomplete. |
| Rust | `Partial` | The documented Rust surface is supported, but lifetime-aware graph semantics remain bounded. | `docs/docs/languages/rust.md`, `go/internal/parser/engine_systems_test.go`, `go/internal/query/code_relationships_rust_graph_test.go` | Macros and lifetime-aware inference remain future work. |
| SQL | `Partial` | The documented SQL/dbt surface is supported, but compiled lineage still has bounded gaps. | `docs/docs/languages/sql.md`, `go/internal/parser/sql_*`, `go/internal/parser/dbt_sql_lineage_parity_test.go` | Unresolved refs, opaque templated expressions, complex macros, and derived expressions remain bounded. |
| Terraform | `Partial` | The documented Terraform surface is supported, but cross-file semantic resolution remains bounded. | `docs/docs/languages/terraform.md`, `go/internal/parser/hcl_terraform_test.go`, `go/internal/query/repository_config_artifacts_*` | `count`/`for_each`, dynamic blocks, and cross-file `var`/`module` references remain partially modeled. |
| Terragrunt | `Partial` | The documented Terragrunt surface is supported, but helper-built HCL remains bounded. | `docs/docs/languages/terragrunt.md`, `go/internal/parser/hcl_terragrunt_test.go`, `go/internal/query/content_relationships_terraform_test.go` | `read_terragrunt_config()` stays opaque and locals keep helper calls as raw text. |
| CloudFormation | `Partial` | The documented CloudFormation surface is supported, but intrinsic-function resolution remains bounded. | `docs/docs/languages/cloudformation.md`, `go/internal/parser/cloudformation_support_test.go`, `go/internal/query/entity_content_cloudformation_fallback_test.go` | `!Ref`, `!Sub`, and `!GetAtt` stay stringly typed. |
| Crossplane | `Partial` | The documented Crossplane surface is supported, but composition transforms remain bounded. | `docs/docs/languages/crossplane.md`, `go/internal/parser/engine_yaml_semantics_test.go` | Patch transforms, validation schema detail, and composition functions stay future work. |
| Helm | `Partial` | The documented Helm surface is supported, but hooks and weight modeling remain bounded. | `docs/docs/languages/helm.md`, `go/internal/parser/engine_yaml_semantics_test.go` | No query/content fallback surface yet and hook metadata remains unstructured. |
| Kubernetes | `Partial` | The documented Kubernetes surface is supported, but selector and CRD modeling remain bounded. | `docs/docs/languages/kubernetes.md`, `go/internal/parser/engine_infra_test.go`, `go/internal/query/content_relationships_k8s_test.go` | Container images are not separate nodes and CRDs stay generic. |
| JSON Config | `Partial` | The documented JSON/dbt surface is supported, but generic JSON remains intentionally shallow. | `docs/docs/languages/json.md`, `go/internal/parser/json_language_test.go`, `go/internal/parser/json_dbt_test.go` | Generic JSON is shallow and dbt lineage keeps bounded gaps for unresolved refs and macros. |

## What This Means Right Now

The bounded graph-readiness slice is closed:

- projector canonical publication
- semantic publication
- Postgres phase-state persistence
- reducer readiness gating
- tests, `go vet`, and `golangci-lint`

The remaining parity work is now concentrated in the partial language families
listed above plus the repo-wide relationship-family proof:

- repo-wide relationship-family proof
- Terraform / Terragrunt helper-path proof against real corpora
- controller/workflow family proof against real repos
- parser feature-matrix proof row by row
- finishing the public docs truth sweep across the full docs tree
