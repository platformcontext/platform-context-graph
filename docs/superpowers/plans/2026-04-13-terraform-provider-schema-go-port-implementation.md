# Terraform Provider Schema Go-Port Implementation Plan

> Execute this plan on the rewrite branch. The goal is deletion of Python
> runtime ownership, not indefinite dual-path maintenance.

## Goal

Move Terraform provider-schema relationship extraction from Python runtime
ownership to Go with feature-for-feature parity.

## Why This Is In Scope

The provider-schema subsystem is still on the normal runtime path today through
`relationships/file_evidence.py` and `relationships/evidence_terraform.py`.
That means the branch is not honestly mergeable as a Go runtime conversion
until this seam is moved or deleted.

## Current Python Source Of Truth

- `src/platform_context_graph/relationships/terraform_evidence/provider_schema.py`
- `src/platform_context_graph/relationships/terraform_evidence/generic.py`
- `src/platform_context_graph/relationships/terraform_evidence/_base.py`
- `src/platform_context_graph/relationships/terraform_evidence/__init__.py`
- `src/platform_context_graph/relationships/evidence_terraform.py`
- `src/platform_context_graph/relationships/file_evidence.py`

Supporting artifacts:

- `src/platform_context_graph/relationships/terraform_evidence/schemas/*.json.gz`
- `scripts/generate_terraform_provider_schema.sh`
- `scripts/package_terraform_schemas.sh`

## Existing Test Truth

- `tests/unit/relationships/test_terraform_provider_schema.py`
- `tests/unit/relationships/test_terraform_evidence_registry.py`
- `tests/unit/relationships/test_terraform_evidence_integration.py`
- `tests/unit/relationships/test_file_evidence.py`
- `tests/unit/relationships/test_relationship_platform_fixture_corpus.py`

These tests define the parity surface. The Go port should add equivalent Go
tests first, then cut callers over, then delete the Python runtime path.

## Proposed Go Package Layout

- `go/internal/relationships/terraformschema/loader.go`
- `go/internal/relationships/terraformschema/loader_test.go`
- `go/internal/relationships/terraformschema/classify.go`
- `go/internal/relationships/terraformschema/classify_test.go`
- `go/internal/relationships/terraformevidence/registry.go`
- `go/internal/relationships/terraformevidence/registry_test.go`
- `go/internal/relationships/terraformevidence/generic.go`
- `go/internal/relationships/terraformevidence/generic_test.go`
- `go/internal/relationships/terraformevidence/runtime.go`
- `go/internal/relationships/terraformevidence/runtime_test.go`

## Execution Chunks

### Chunk 1: Lock loader and classifier parity in Go tests

- write failing Go tests for:
  - JSON and `.json.gz` loading
  - missing schema behavior
  - provider/resource metadata parsing
  - identity-key inference rules
  - service-category classification rules
- port only the loader/classifier behavior required by those tests

### Chunk 2: Port registry and generic extractor semantics

- write failing Go tests for:
  - extractor registration
  - handwritten override preservation
  - registered-type lookup
  - generic extractor evidence shape
- implement the registry and generic extractor builder

### Chunk 3: Port runtime Terraform evidence orchestration

- write failing Go tests for:
  - startup-time registration behavior
  - schema-directory discovery
  - integration into the Terraform evidence runtime flow
- implement the Go runtime orchestration package

### Chunk 4: Cut the normal runtime path to Go

- replace the live Terraform evidence call path so normal runtime extraction
  enters through Go-owned logic
- keep the hot path honest: no Python bridge wrappers on the normal path

### Chunk 5: Delete Python runtime ownership

- delete:
  - `src/platform_context_graph/relationships/terraform_evidence/__init__.py`
  - `src/platform_context_graph/relationships/terraform_evidence/generic.py`
  - `src/platform_context_graph/relationships/terraform_evidence/_base.py`
  - `src/platform_context_graph/relationships/terraform_evidence/provider_schema.py`
  - remaining Python runtime wiring in `evidence_terraform.py` once callers are cut
- update docs and tests to reflect Go ownership

## Validation

Smallest-first validation order:

```bash
cd go
go test ./internal/relationships/terraformschema ./internal/relationships/terraformevidence -count=1
```

Then broader parity and docs checks:

```bash
PYTHONPATH=src uv run python -m pytest \
  tests/unit/relationships/test_terraform_provider_schema.py \
  tests/unit/relationships/test_terraform_evidence_registry.py \
  tests/unit/relationships/test_terraform_evidence_integration.py -q

uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml

git diff --check
```

## Safe Deletion Order

Delete callers last, not first:

1. cut the runtime call path to Go
2. remove Python runtime registration/orchestration
3. remove Python registry/generic helpers
4. remove Python schema loader/classifier

This keeps the branch truthful while avoiding a half-cut state where docs say
Go but runtime still depends on Python imports.
