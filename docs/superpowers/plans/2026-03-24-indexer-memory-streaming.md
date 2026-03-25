# Execution Plan: Memory Streaming and Repository Truthfulness Reset

## Scope

Keep all work on `codex/indexer-memory-streaming` and ship one PR that:

- removes corpus-wide in-memory retention from checkpointed indexing
- adds durable per-run repository coverage
- resets repository context/stats semantics around recursive counts
- makes the Neo4j/Postgres/runtime contract explicit in HTTP and MCP surfaces
- validates the full story locally against `boatgest-php-youboat`

## Work Items

1. Finish checkpoint artifact split and resume durability.
   - metadata written only after file-data
   - resume reparses when file-data is missing

2. Finalize from committed repo paths instead of retained snapshots.
   - lazy file-data loads
   - incremental function-call flushing
   - memory diagnostics around commit/finalization
   - remove the temporary vendored-only `CALLS` policy once discovery excludes
     dependency trees directly

3. Persist repository coverage durably.
   - add `runtime_repository_coverage`
   - publish rows during discovery, parse, commit, and finalization
   - add a backfill CLI for the active/latest run

4. Reset repository query semantics.
   - canonical `repo_id` only
   - recursive `file_count`
   - explicit `root_file_count`
   - explicit `root_directory_count`
   - total `functions`
   - explicit `top_level_functions`
   - explicit `class_methods`
   - explicit `classes`

5. Expose repository coverage and truthful runtime status.
   - HTTP repository coverage endpoint
   - HTTP run-level coverage listing endpoint
   - MCP `get_repository_coverage`
   - MCP `list_repository_coverage`
   - MCP `get_index_status` callable through dispatch
   - checkpoint-aware runtime status fallback when persistence lags

6. Fix the local Compose validation path.
   - API service gets the same repo-source env as bootstrap
   - API service is available during bootstrap instead of waiting for bootstrap
     completion

7. Make long-running commit truth visible without overstating committed counts.
   - batch persistence emits per-file commit heartbeats
   - runtime status refreshes `active_current_file` and `active_last_progress_at`
     during a long batch
   - repository coverage remains committed truth instead of pretending
     uncommitted counts are durable

8. Make coverage publishing fail open when graph counting is unavailable.
   - skip coverage row updates when Neo4j count queries fail
   - preserve the last committed coverage row
   - do not let coverage publishing abort bootstrap indexing

9. Validate locally against `/Users/allen/repos/testing/boatgest-php-youboat`.
   - HTTP health/status/context/stats/coverage
   - content file/entity search and read
    - local MCP JSON-RPC tool calls
    - direct Neo4j and Postgres counts
   - prove that `vendor/` is absent from graph/content storage for the default
     path
   - prove that first-party files remain indexed

10. Default-exclude vendored and dependency directories.
   - add an exhaustive built-in dependency-root catalog across supported
     ecosystems
   - add `PCG_IGNORE_DEPENDENCY_DIRS=true` as the default toggle
   - keep Helm `charts/` indexed by default
   - ensure dependency trees never enter checkpoints, Neo4j, Postgres,
     coverage, or finalization

11. Add explicit dependency opt-in via bundles.
   - HTTP `POST /api/v0/bundles/import`
   - CLI `pcg bundle upload <bundle-file> --service-url <base-url> [--clear]`
   - keep local bundle import/load and MCP `load_bundle`

12. Use the local result set to update the PR description.
   - memory fix
   - storage contract
   - repository truthfulness reset
   - large-repo validation evidence
   - default dependency exclusion contract
   - bundle upload/import path for dependency internals
   - manual ops-qa reset and fresh reindex plan

## Verification

- targeted unit tests for checkpoint durability
- targeted unit tests for runtime status fallback
- targeted unit tests for repository query semantics
- targeted unit tests for coverage persistence/backfill
- integration tests for repository API and MCP tool parity
- dependency-catalog and discovery tests covering `vendor/`, `node_modules/`,
  and Helm `charts/`
- HTTP and CLI bundle-upload tests
- local Docker Compose validation against `boatgest-php-youboat`

## Release Gate

The release gate is:

- no resume regression for partial checkpoints
- active bootstrap progress visible through status APIs/tools
- repository context, stats, and coverage agree on the same repo
- direct Neo4j counts match repository graph counts
- direct Postgres counts match content availability and coverage counts
- local MCP and HTTP surfaces report the same durable truth
- dependency trees are absent from default first-party indexing
- large local runs no longer die from the previous OOM path; if they still stop,
  the stopping reason must be explicit in status/logging
