# Developing PlatformContextGraph

This document is for anyone writing code in this repo. It covers how the
Go-owned parser system works, how to add language or IaC support, and how to
validate runtime changes honestly on the migration branch.

For general contribution rules, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Development Environment

```bash
go version
cd go && go test ./cmd/pcg -count=1
```

Pre-PR checks:

```bash
cd go
go test ./cmd/pcg ./cmd/api ./cmd/mcp-server ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer -count=1
go test ./internal/parser ./internal/collector ./internal/query ./internal/runtime ./internal/reducer ./internal/projector -count=1
go test ./internal/terraformschema ./internal/relationships ./internal/storage/postgres -count=1
golangci-lint run ./...
```

## Parser Architecture

PCG now uses a Go-owned parser platform rooted in `go/internal/parser/`.

### Registry And Dispatch

- `registry.go` owns parser-key and extension dispatch
- `engine.go` owns per-file parse execution
- `runtime.go` owns tree-sitter bootstrap and parser construction
- `scip_support.go` and `scip_parser.go` own SCIP ingestion paths

The parser engine dispatches by file type and returns a normalized payload that
feeds collector facts, content shaping, projector stages, and reducer domains.

### Language Families

The parser platform covers:

- managed OO languages
- scripting languages
- systems languages
- infrastructure formats
- SQL and data-intelligence formats
- raw-text fallback where intentional

Representative test coverage lives under:

- `go/internal/parser/engine_test.go`
- `go/internal/parser/engine_managed_oo_test.go`
- `go/internal/parser/engine_python_semantics_test.go`
- `go/internal/parser/engine_javascript_semantics_test.go`
- `go/internal/parser/engine_systems_test.go`
- `go/internal/parser/engine_infra_test.go`
- `go/internal/parser/engine_sql_test.go`
- `go/internal/parser/json_dbt_test.go`

### IaC And Schema-Driven Parsing

Infrastructure parsing is split deliberately:

- `go/internal/parser/` handles raw file parsing and semantic extraction
- `go/internal/relationships/` handles repo-to-repo and infra relationship
  discovery
- `go/internal/terraformschema/` owns packaged Terraform provider schemas,
  identity-key inference, and category classification

Terraform provider schemas are runtime assets, not just generated fixtures. If
you change how Terraform extraction works, update the packaged schema path and
the operator docs together.

## Adding A New Parser Capability

1. Write or extend a fixture under `tests/fixtures/`.
2. Add a focused Go test under `go/internal/parser/`.
3. Implement the parser change in `go/internal/parser/`.
4. If the change affects relationship extraction or content shaping, add the
   corresponding test under `go/internal/relationships/` or
   `go/internal/content/shape/`.
5. Update the affected docs under `docs/docs/`.

### Rules

- Start with tests.
- Keep parser/runtime ownership in Go.
- Do not add a compatibility bridge or resurrect deleted Python modules.
- Keep normal-path parser semantics inside the native engine rather than in the
  CLI or collector shells.

## Runtime Development

The service boundary is explicit:

- `go/cmd/api/`
- `go/cmd/mcp-server/`
- `go/cmd/bootstrap-index/`
- `go/cmd/ingester/`
- `go/cmd/reducer/`
- `go/cmd/pcg/`

Shared runtime concerns live under:

- `go/internal/runtime/`
- `go/internal/status/`
- `go/internal/telemetry/`
- `go/internal/storage/`

If a change affects probes, retries, admin/status, or recovery, update both the
runtime package tests and the operator docs.

## Integration And Compose Proof

Use the compose proof scripts for cross-service validation:

```bash
./scripts/verify_collector_git_runtime_compose.sh
./scripts/verify_projector_runtime_compose.sh
./scripts/verify_reducer_runtime_compose.sh
./scripts/verify_incremental_refresh_compose.sh
./scripts/verify_relationship_platform_compose.sh
./scripts/verify_admin_refinalize_compose.sh
```

Use `docs/docs/reference/local-testing.md` as the source of truth for when each
proof is required.
