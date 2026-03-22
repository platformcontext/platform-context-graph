# Compose Host Root Override Design

## Goal

Allow the checked-in Docker Compose files to index a caller-specified host source root while keeping the default local experience fixture-backed.

## Requirements

- Keep the checked-in default behavior pointed at `./tests/fixtures/ecosystems`.
- Support overriding the host-side filesystem source root for real local end-to-end runs.
- Preserve the container-side runtime contract:
  - `PCG_REPO_SOURCE_MODE=filesystem`
  - `PCG_FILESYSTEM_ROOT=/fixtures`
- Keep `docker-compose.yaml` and `docker-compose.template.yml` aligned.
- Document the real local E2E invocation pattern using an absolute host path such as `$HOME/repos/mobius`.

## Chosen Approach

Use one environment override in the checked-in Compose files:

- `PCG_FILESYSTEM_HOST_ROOT`

The bind mounts for `bootstrap-index` and `repo-sync` will change from the fixed fixture path to:

- `${PCG_FILESYSTEM_HOST_ROOT:-./tests/fixtures/ecosystems}:/fixtures:ro`

This keeps the runtime internals stable and limits the change to Compose rendering plus docs and tests.

## Why This Approach

- Smallest possible change to satisfy the requirement.
- No new runtime configuration branches.
- Existing fixture-based smoke tests still work by default.
- Real local E2E runs can target sensitive day-job repos without checking those paths into the repository.

## Validation

- Add a deployment rendering test proving the host-root override appears in `docker-compose config`.
- Update docs to show the absolute-path override command.
- Use the override in the final local E2E run against `~/repos/mobius`.
