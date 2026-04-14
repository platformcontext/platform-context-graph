# Terraform Provider Schema Go-Port Checklist

## Purpose

Track feature-for-feature parity for the Terraform provider-schema subsystem
before the branch can claim full Python-to-Go runtime conversion.

This subsystem is still live on the normal runtime path today. It is not just
offline packaging.

Current Python runtime path:

- `src/platform_context_graph/relationships/execution.py`
- `src/platform_context_graph/relationships/file_evidence.py`
- `src/platform_context_graph/relationships/evidence_terraform.py`
- `src/platform_context_graph/relationships/terraform_evidence/__init__.py`
- `src/platform_context_graph/relationships/terraform_evidence/generic.py`
- `src/platform_context_graph/relationships/terraform_evidence/provider_schema.py`

## Runtime Behaviors That Must Match

- load both plain JSON and `.json.gz` Terraform provider schema files
- support `PCG_TERRAFORM_SCHEMA_DIR` override before bundled schema lookup
- use `go/internal/terraformschema/schemas/*.json.gz` as the canonical bundled
  schema location
- parse provider/resource metadata from `provider_schemas`
- infer identity keys using the same ordered fallback rules
- classify service category using the same longest-prefix resource matching
- register schema-driven generic extractors by resource type
- skip handwritten overrides instead of replacing them
- preserve the same confidence and evidence-kind behavior for generic
  extractors
- preserve startup-time registration semantics for the normal runtime path
- integrate into the same Terraform relationship-evidence flow

## Source Of Truth Files

- `src/platform_context_graph/relationships/terraform_evidence/provider_schema.py`
- `src/platform_context_graph/relationships/terraform_evidence/generic.py`
- `src/platform_context_graph/relationships/terraform_evidence/_base.py`
- `src/platform_context_graph/relationships/terraform_evidence/__init__.py`
- `src/platform_context_graph/relationships/evidence_terraform.py`
- `src/platform_context_graph/relationships/file_evidence.py`
- `scripts/generate_terraform_provider_schema.sh`
- `scripts/package_terraform_schemas.sh`

## Existing Parity Tests

- `tests/unit/relationships/test_terraform_provider_schema.py`
- `tests/unit/relationships/test_terraform_evidence_registry.py`
- `tests/unit/relationships/test_terraform_evidence_integration.py`
- `tests/unit/relationships/test_file_evidence.py`
- `tests/unit/relationships/test_relationship_platform_fixture_corpus.py`

## Proposed Go Runtime Surface

- `go/internal/relationships/terraformschema/`
- `go/internal/relationships/terraformevidence/`

Minimum packages:

- schema loader and classifier
- extractor registry
- generic extractor builder
- runtime orchestration for Terraform evidence

## Completion Bar

This migration slice is complete only when all of the following are true:

- no normal runtime Terraform evidence path depends on
  `src/platform_context_graph/relationships/terraform_evidence/**`
- the Go runtime loads bundled and overridden provider schema files
- the Go runtime emits equivalent generic Terraform evidence for supported
  providers
- parity tests exist for loader, classifier, registry, extractor, and
  integration behavior
- runtime docs and Terraform provider docs describe the Go-owned path truthfully
- Python runtime ownership for this subsystem is deleted, not just bypassed in
  docs
