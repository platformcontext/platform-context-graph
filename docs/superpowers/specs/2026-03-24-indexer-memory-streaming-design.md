# Indexer Memory Streaming and Repository Truthfulness Reset

## Summary

This branch solves two linked problems in the repository indexing pipeline:

1. memory instability during large checkpointed indexing runs
2. ambiguous repository truth surfaces that make partial or in-progress indexes
   look more complete or less complete than they actually are

The new durable contract is explicit:

- `Neo4j` is the source of truth for graph structure and graph-derived counts
- `Postgres` is the source of truth for file/entity content and content search
- runtime/checkpoint state is the source of truth for indexing progress, active
  phase, and run completion
- repository completeness is exposed through durable per-run coverage rows

This is intentionally a contract reset. There are no downstream consumers that
need the old ambiguous semantics preserved.

## Problems

### Memory instability

The checkpointed batch indexer had two independent memory accumulators:

1. commit-time accumulation
   `process_repository_snapshots()` kept committed `RepositorySnapshot`
   instances alive after commit
2. finalization-time accumulation
   `finalize_index_batch()` rebuilt a corpus-wide `all_file_data` list and
   function-call finalization accumulated run-wide call rows before flushing

In production-like runs this pushed the ingester to roughly `22Gi` and led to
`OOMKilled` restarts.

### Repository truthfulness drift

The system exposed several overlapping but semantically different repository
surfaces:

- repository context counted only some function shapes in some places
- repository stats counted total recursive functions elsewhere
- root-level repository contents were easy to confuse with recursive totals
- `repo_access.state=needs_local_checkout` could be misread as “server content
  unavailable” even when Postgres-backed content search worked
- runtime bootstrap progress could look stuck as `bootstrap_pending` even while
  checkpointed indexing was actively parsing or committing
- MCP `tools/list` and `tools/call` had drift for runtime tools

The result was user confusion around large repositories such as
`boatgest-php-youboat`, especially while a run was still active.

## Goals

- bound commit and finalization memory
- preserve checkpoint/resume durability
- expose active indexing progress durably while a run is in flight
- expose repository completeness durably per run
- make repository context, repository stats, and repository coverage tell one
  coherent story
- make the Neo4j/Postgres/runtime storage contract explicit in public API and
  MCP surfaces

## Non-Goals

- reducing pod limits in this change
- renderer-generated content
- page-cache tuning
- archived-run cleanup
- preserving old name/path-first repository query semantics

## Design

### Memory streaming

Per-repository checkpoint persistence is split into two artifacts:

- metadata artifact
  - `repo_path`
  - `file_count`
  - `imports_map`
- heavyweight file-data artifact
  - `file_data`

Durability rules:

- file-data is written first
- metadata is written second
- metadata acts as the completion marker
- resume reuses a repo only when both artifacts exist

Commit/finalization rules:

- the parse/commit pipeline returns committed repository paths, not in-memory
  snapshots
- finalization lazily reloads file data from disk per repository
- function-call finalization flushes incrementally instead of building one
  run-wide row buffer

### Dependency directory policy

Dependency and vendored trees are now excluded at discovery time by default.

Contract:

- first-party repository indexing excludes built-in dependency and tool-managed
  cache roots before parse
- excluded paths never enter checkpoints, Neo4j, Postgres, coverage counts, or
  finalization
- `.pcgignore` remains a repo-local override for project-specific exclusions,
  not the primary dependency policy
- Helm `charts/` remain indexed because they can contain first-party subcharts
- dependency internals come back in only through an explicit `.pcg` bundle load
  or separate dependency indexing workflow

The default toggle is:

- `PCG_IGNORE_DEPENDENCY_DIRS=true`

The built-in catalog is exhaustive across supported ecosystems. Canonical roots
currently excluded include:

- JavaScript and TypeScript: `node_modules/`, `bower_components/`,
  `jspm_packages/`
- Python: `site-packages/`, `dist-packages/`, `__pypackages__/`
- PHP: `vendor/`
- Go: `vendor/`
- Ruby: `vendor/bundle/`
- Elixir: `deps/`
- Swift ecosystem: `Carthage/Checkouts/`, `.build/checkouts/`, `Pods/`
- IaC and tool-managed caches: `.terraform/`, `.terragrunt-cache/`, `.pulumi/`,
  `.serverless/`, `.aws-sam/`, `.crossplane/`, `cdk.out/`,
  `.terramate-cache/`

Supported ecosystems without a single stable in-repo dependency root are
recorded explicitly as `none` in the catalog rather than inferred ad hoc.

### Bundle import

Dependency context is opt-in through `.pcg` bundles.

Supported flows:

- local CLI import: `pcg bundle import /path/to/library.pcg`
- local or registry load: `pcg bundle load <name-or-file>`
- remote HTTP upload: `POST /api/v0/bundles/import`
- remote CLI wrapper: `pcg bundle upload <bundle-file> --service-url <base-url>`

This keeps routine repository indexing focused on first-party code while still
allowing teams to load dependency internals deliberately when they need them.

### Durable repository coverage

Add `runtime_repository_coverage` in PostgreSQL as a per-run, per-repo truth
table.

Each row persists:

- repository identity
- checkpoint run identity
- status and phase
- finalization status
- discovered file count
- graph counts from Neo4j
- content counts from Postgres
- root-vs-recursive file counts
- top-level functions vs class methods vs total functions
- graph/content availability flags
- last error and lifecycle timestamps

Coverage is updated:

- when a repo is discovered
- after parse
- after commit
- after finalization

Coverage rows are preserved for partial, failed, and completed repos.

### Public truth contract

Repository APIs and MCP tools now operate on canonical `repo_id` values.

Public semantics:

- `repository.file_count` means recursive `File` count
- `repository.root_file_count` means direct `Repository -> File` count
- `repository.root_directory_count` means direct `Repository -> Directory`
  count
- `code.functions` means total recursive `Function` count
- `code.top_level_functions` means file-contained functions
- `code.class_methods` means functions contained by non-file nodes such as
  classes
- `code.classes` means recursive `Class` count

Repository responses also expose:

- `graph_available`
- `server_content_available`
- `index_status`
- `active_run_id`

`repo_access` is no longer treated as a repository-summary signal. It remains a
content-tool handoff mechanism only when the server needs client-local checkout
help.

### Runtime status truth

Runtime status now has two layers:

- durable PostgreSQL runtime status rows when available
- checkpoint-derived fallback from `run.json` when persistence lags or is not
  yet updated

The status query prefers the active checkpoint summary over stale
`bootstrap_pending` persistence so active bootstrap work becomes visible.

### MCP parity

MCP tool registry and tool dispatch now cover the same runtime/repository tools.

Required callable tools include:

- `get_index_status`
- `get_repository_coverage`
- `list_repository_coverage`

## Validation Story

### Local validation

The branch is validated locally against a real large PHP repository:

- filesystem root: `/Users/allen/repos/testing`
- repository: `/Users/allen/repos/testing/boatgest-php-youboat`

Validation uses Docker Compose plus:

- direct Neo4j counts
- direct Postgres counts
- HTTP repository/content endpoints
- MCP JSON-RPC calls

Important observed truth:

- the repo is large and indexes successfully
- long bootstrap phases can look stale if a user inspects only one status file
  at the wrong moment
- Postgres content can become available before finalization completes
- root counts and recursive counts must be shown separately or the repo looks
  falsely incomplete
- after the streaming checkpoint replay change, the old local `OOMKilled`
  failure moved: bootstrap progressed far past the previous ~`850` file plateau
  and reached roughly `2193` Postgres `content_files`, `52374`
  `content_entities`, `2150` Neo4j `File` nodes, `17035` `Function` nodes, and
  `41` `Class` nodes before stopping
- the new local blocker was Neo4j disk exhaustion (`No space left on device`),
  not process memory pressure
- runtime liveness and durable coverage need to be separated:
  - runtime status should move during a long commit batch as files are processed
  - repository coverage should remain committed truth and only refresh from
    durable graph/content counts
- repository coverage publishing must fail open when Neo4j is unhealthy so a
  graph-store outage does not abort the indexing run while preserving the last
  good committed coverage row
- `function_calls` had been dominated by vendored JavaScript and vendored PHP
  trees; moving dependency exclusion to discovery removes those files from the
  corpus entirely instead of carrying them into later stages and suppressing
  them there

### QA validation

The same contract is intended for QA MCP validation against:

- `https://mcp-pcg.qa.ops.bgrp.io/mcp/message`

The new repository coverage surfaces make the active run auditable without
forcing a rerun.

## Rollout

1. validate unit and integration coverage locally
2. validate the checked-in Compose stack against `boatgest-php-youboat`
3. deploy to QA
4. backfill repository coverage rows for the active/latest run
5. confirm repository context/stats/coverage and MCP runtime tools tell the same
   story
6. only after a successful full run consider pod limit tuning

## Deferred Work

- pod resource tuning
- archived-run cleanup
- rendered/template-derived content
- deeper Postgres performance tuning
- page-cache tuning and allocator trimming as primary mechanisms
- increasing local Docker Desktop disk capacity or pruning local image/cache
  usage before the next full-repo local rerun
