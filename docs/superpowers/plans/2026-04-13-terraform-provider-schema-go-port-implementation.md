# Terraform Provider Schema Go-Port Implementation Plan

> **Status: completed.** All Python runtime ownership for Terraform
> provider-schema relationship extraction has been deleted from this branch.
> The Go runtime is the sole owner. This document is retained as historical
> context for the migration.

## Goal

Move Terraform provider-schema relationship extraction from Python runtime
ownership to Go with feature-for-feature parity.

## Outcome

All Python source files listed below have been deleted. The Go runtime now
owns schema loading, identity-key inference, category classification, and
schema-driven generic Terraform evidence emission end to end.

## Former Python Source Of Truth (deleted)

- `src/platform_context_graph/relationships/terraform_evidence/provider_schema.py`
- `src/platform_context_graph/relationships/terraform_evidence/generic.py`
- `src/platform_context_graph/relationships/terraform_evidence/_base.py`
- `src/platform_context_graph/relationships/terraform_evidence/__init__.py`
- `src/platform_context_graph/relationships/evidence_terraform.py`
- `src/platform_context_graph/relationships/file_evidence.py`

Supporting artifacts (still present):

- `go/internal/terraformschema/schemas/*.json.gz` (canonical packaged path)
- `scripts/generate_terraform_provider_schema.sh`
- `scripts/package_terraform_schemas.sh`

## Former Python Test Truth (deleted with Python runtime)

- `tests/unit/relationships/test_terraform_provider_schema.py`
- `tests/unit/relationships/test_terraform_evidence_registry.py`
- `tests/unit/relationships/test_terraform_evidence_integration.py`
- `tests/unit/relationships/test_file_evidence.py`
- `tests/unit/relationships/test_relationship_platform_fixture_corpus.py`

Equivalent Go tests now live in `go/internal/terraformschema/*_test.go` and
`go/internal/relationships/*_test.go`.

## Current Go Layout

Landed on this branch:

- `go/internal/terraformschema/schema.go`
- `go/internal/terraformschema/categories.go`
- `go/internal/terraformschema/*_test.go`
- `go/internal/relationships/terraform_schema.go`
- `go/internal/relationships/terraform_schema*_test.go`

This means the Go side now owns:

- plain JSON and `.json.gz` schema loading
- nested `metadata` attribute merge for identity discovery
- identity-key inference parity
- longest-prefix service-category classification parity
- schema-driven Terraform generic extractor registration
- schema-driven Terraform evidence emission inside the Go
  `internal/relationships` runtime

Cut over and deleted — no Python runtime ownership remains.

## Execution Chunks

### Chunk 1: Lock loader and classifier parity in Go tests

Status: done on this branch.

- write failing Go tests for:
  - JSON and `.json.gz` loading
  - missing schema behavior
  - provider/resource metadata parsing
  - identity-key inference rules
  - service-category classification rules
- port only the loader/classifier behavior required by those tests

### Chunk 2: Port registry and generic extractor semantics

Status: done on this branch.

- write failing Go tests for:
  - extractor registration
  - handwritten override preservation
  - registered-type lookup
  - generic extractor evidence shape
- implement the registry and generic extractor builder

### Chunk 3: Port runtime Terraform evidence orchestration

Status: done on this branch.

### Chunk 4: Cut the normal runtime path to Go

Status: done on this branch.

### Chunk 5: Delete Python runtime ownership

Status: done on this branch. All Python files listed above have been deleted.

## Validation

Smallest-first validation order:

```bash
cd go
go test ./internal/terraformschema ./internal/relationships -count=1
golangci-lint run ./internal/terraformschema/... ./internal/relationships/...
```

Then docs checks:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml

git diff --check
```
