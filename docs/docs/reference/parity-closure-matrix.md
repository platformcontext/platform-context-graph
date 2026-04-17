# Parity Closure Matrix

This page records the current code-backed truth of the Go platform.

A row is only marked `Closed` when the behavior is implemented in Go and backed
by direct code inspection plus targeted tests or validation on this branch.

Use this page to answer:

- what is already closed in Go
- what is only partially closed
- what still needs a targeted parity push before cutover

## Status Legend

| Status | Meaning |
| --- | --- |
| `Closed` | Implemented in Go and directly validated from code plus focused tests |
| `Partial` | Implemented in part, or documented broadly but not fully re-audited end to end |
| `Open` | Still needs targeted implementation or full proof before claiming parity |

## Current Matrix

| Area | Status | Current truth | Primary evidence | What still needs closure |
| --- | --- | --- | --- | --- |
| Long-running Go runtimes | `Closed` | API, MCP, ingester, reducer, and bootstrap runtime shapes are Go-owned | `go/cmd/api`, `go/cmd/mcp-server`, `go/cmd/ingester`, `go/cmd/reducer`, `go/cmd/bootstrap-index`; runtime docs and local testing runbook | Keep deployment docs aligned as runtime wiring evolves |
| Shared runtime admin contract | `Closed` | `/healthz`, `/readyz`, `/admin/status`, and optional `/metrics` are mounted through shared Go runtime packages | `go/internal/runtime/*`, `go/internal/status/*`, `docs/docs/reference/runtime-admin-api.md` | Continue using the shared contract for new services instead of bespoke probes |
| Structured Go telemetry | `Closed` | Go runtimes emit JSON logs plus OTEL metrics/traces through shared telemetry packages | `go/internal/runtime/observability.go`, `go/internal/telemetry` references in docs and tests | Keep field names stable for operator tooling |
| Terraform provider-schema packaging | `Closed` | Provider schemas are packaged in-repo and loaded from `go/internal/terraformschema/schemas/*.json.gz` | `go/internal/terraformschema/*`, provider docs under `docs/docs/guides/terraform-providers/` | Broader provider coverage can expand later without changing runtime ownership |
| Projector canonical readiness publication | `Closed` | Projector publishes `canonical_nodes_committed` after canonical node writes succeed | `go/internal/projector/runtime.go`, `go/internal/projector/runtime_test.go::TestRuntimeProjectPublishesCanonicalNodesCommittedAfterCanonicalWrite` | None in this slice beyond broader end-to-end corpus proof |
| Reducer semantic readiness publication | `Closed` | Semantic-entity materialization publishes `semantic_nodes_committed` after semantic node writes succeed | `go/internal/reducer/semantic_entity_materialization.go`, `go/internal/reducer/semantic_entity_materialization_test.go::TestSemanticEntityMaterializationPublishesSemanticNodesCommitted` | None in this slice beyond broader end-to-end corpus proof |
| Durable phase-state storage | `Closed` | Bounded graph-readiness state is stored in Postgres `graph_projection_phase_state` and included in bootstrap schema order | `go/internal/storage/postgres/graph_projection_phase_state.go`, `go/internal/storage/postgres/graph_projection_phase_state_test.go`, `schema/data-plane/postgres/012_graph_projection_phase_state.sql`, `go/internal/storage/postgres/schema_test.go` | None for this slice |
| Shared edge readiness gating | `Closed` | Shared edge domains wait on semantic readiness before writing when they require semantic node presence | `go/internal/reducer/shared_projection.go`, `shared_projection_worker.go`, `code_call_projection_runner.go`, related tests | End-to-end fixture proof across larger corpora |
| Code calls / SQL / inheritance edge domains | `Closed` | These domains are explicitly gated by semantic readiness in reducer flow | `domainRequiresSemanticNodeReadiness` and related tests in `go/internal/reducer` | Keep docs aligned if more domains join the gating set |
| Relationship verb contract | `Partial` | Public docs define the canonical verb set and Go code clearly covers multiple typed families, but repo-wide proof for every documented family was not re-run in this pass | `docs/docs/reference/relationship-mapping.md`, `go/internal/relationships/*`, `go/internal/query/*` | Final targeted audit for each public verb family with fixture or corpus evidence |
| GitHub Actions relationship evidence | `Partial` | Go relationship/query code clearly contains GitHub Actions evidence extraction and read-path shaping | `go/internal/relationships/github_actions_evidence.go`, `go/internal/query/content_relationships_github_actions.go`, related tests | Final end-to-end proof against local real-world workflow repos |
| Jenkins / Ansible controller-driven evidence | `Partial` | Go relationship layer includes Jenkins and Ansible evidence extraction and tests | `go/internal/relationships/jenkins_evidence.go`, `ansible_evidence.go`, `ansible_jenkins_fixture_test.go` | Final corpus validation against local repos and query surfaces |
| Docker / Compose relationship evidence | `Partial` | Go relationship layer includes Dockerfile and Docker Compose evidence extraction | `go/internal/relationships/dockerfile_evidence.go`, `docker_compose_evidence.go`, related tests | Final query-surface validation and mixed-repo corpus proof |
| Terraform / Terragrunt helper-path relationship coverage | `Partial` | Public docs describe broad helper-built path-expression support; code clearly includes Terraform schema and relationship extraction, but the full documented helper matrix was not re-audited in this pass | `go/internal/relationships/terraform_schema.go`, `terragrunt_helper_evidence.go`, `go/internal/query/repository_*`, `docs/docs/reference/relationship-mapping.md` | Targeted parity audit against local Terraform/Terragrunt repos, especially helper-built and module-source cases |
| Public docs truth for runtime/readiness flow | `Closed` | Public docs now describe projector/reducer phase readiness as implemented in Go instead of implying hidden coupling | this page plus `service-runtimes.md`, `service-workflows.md`, `relationship-mapping.md`, `telemetry/index.md` | Keep docs current as code changes land |
| Repo-wide docs truth for every language and feature page | `Partial` | Major public runtime/docs cleanup is already landed, but the full `docs/docs` tree still needs a systematic line-by-line truth sweep against code | current public docs plus targeted scans | Continue doc audit by feature family until every public claim is evidence-backed |
| Full parser family parity proof | `Partial` | Go parser platform is broad and public language pages exist, but this pass did not re-prove every documented feature row against code and fixtures | `docs/docs/languages/*`, parser tests under `go/internal/parser` | Complete row-by-row parser parity audit and fill any remaining gaps |

## What This Means Right Now

The bounded graph-readiness slice is closed:

- projector canonical publication
- semantic publication
- Postgres phase-state persistence
- reducer readiness gating
- tests, `go vet`, and `golangci-lint`

The remaining parity work is now mostly concentrated in:

- repo-wide relationship-family proof
- Terraform / Terragrunt helper-path proof against real corpora
- controller/workflow family proof against real repos
- parser feature-matrix proof row by row
- finishing the public docs truth sweep across the full docs tree
