# Raw Content Metadata for Templated and IaC Artifacts

## Summary

Platform Context Graph already indexes raw source content into PostgreSQL and exposes it through the existing HTTP and MCP content read/search surfaces. Recent work added raw-text ingestion for Dockerfiles, config templates, Terraform templates, and related text artifacts, plus a sanitized fixture corpus that proves those files are searchable as authored source.

What is still missing is durable metadata that tells clients what kind of artifact a file or entity represents. Today, clients can only filter on coarse `language` values. That is enough to find text, but not enough to distinguish:

- Helm helpers from Terraform templates
- templated YAML from plain YAML
- Dockerfiles from generic text
- IaC-relevant files from non-IaC files

This design adds additive metadata to existing content rows and existing content APIs. Raw source remains canonical. Rendered/generated output is explicitly deferred.

## Goals

- Persist durable metadata on indexed file and entity content rows.
- Reuse a single shared classifier so indexing, backfill, API responses, and tests agree on metadata values.
- Expose metadata through the current HTTP and MCP content surfaces without adding new endpoints.
- Support metadata-based filtering for both file-content and entity-content search.
- Backfill existing rows without forcing repository changes or a global reindex.

## Non-Goals

- Storing rendered/generated template output.
- Rendering Helm, Jinja, Ansible, Argo, or Terraform templates during indexing.
- Adding new HTTP endpoints or MCP tools.
- Classifying entity snippets independently from their containing file.

## Metadata Model

Persist the following additive fields on both `content_files` and `content_entities`:

- `artifact_type TEXT NULL`
- `template_dialect TEXT NULL`
- `iac_relevant BOOLEAN NULL`

`language` remains unchanged and backward compatible. The new metadata fields are the richer, more specific classification layer.

### Initial artifact families

The shared classifier should surface at least these v1 artifact families:

- `helm_helper_tpl`
- `go_template_yaml`
- `jinja_yaml`
- `terraform_hcl`
- `terraform_template_text`
- `dockerfile`
- `docker_compose`
- `apache_config`
- `nginx_config`
- `generic_config`
- `jinja_text_template`
- `github_actions_workflow`
- `yaml_document`

Not every file needs a non-null `artifact_type`. Ordinary code files can remain `NULL`/not-IaC.

### Template dialect values

Normalize template dialects to a small stable vocabulary:

- `go_template`
- `jinja`
- `terraform_template`
- `github_actions`

Mixed or ambiguous files fail closed to `template_dialect = NULL`.

### Entity inheritance

Entity metadata is inherited from the containing file classification. This keeps the behavior deterministic and avoids trying to classify source snippets out of context.

## Architecture

### Shared classifier

Promote the spike detection logic into the production path and expose a production helper that infers metadata from:

- `relative_path`
- raw file content

The inventory-only `root_family` input should remain an implementation detail for the repo-scanning spike, not a production contract.

### Ingest path

During content dual-write:

1. classify the file once
2. stamp metadata onto the `content_files` row
3. stamp the same metadata onto every `content_entities` row derived from that file

### Search and read path

Extend the current file and entity content responses with the new metadata fields. Extend the existing search requests with optional filters:

- `artifact_types`
- `template_dialects`
- `iac_relevant`

These are additive only. Existing callers continue to work unchanged.

### Backfill

Because unchanged repos do not reindex automatically, add a one-time metadata backfill command that:

- scans existing `content_files` rows in ordered batches
- reclassifies from raw stored content
- updates `content_files`
- cascades the same metadata to `content_entities` by `(repo_id, relative_path)`

The backfill must be idempotent, batch-driven, and resumable by rerun.

## Testing Strategy

### Unit

- classifier coverage over the sanitized fixture corpus
- file/entity ingest metadata propagation
- Postgres content row persistence and metadata filters
- content service, API, and MCP filter plumbing
- backfill dry-run, scoped run, and idempotency

### End-to-end

Use the sanitized fixture corpus to prove:

- Dockerfiles, Helm helpers, Jinja configs, Jinja YAML, and Terraform templates are still searchable as raw source
- file and entity search can now filter by metadata
- `iac_relevant=true` isolates the fixture corpus cleanly

## Future Work: Rendered Artifacts

Rendered/generated output is intentionally out of scope for this wave.

If added later, it should be designed as a separate subsystem with:

- separate storage from canonical raw source
- renderer provenance
- deterministic offline-renderer constraints
- no requirement to support every template dialect

The recommended starting point for any future rendered-artifacts work is Helm only.
