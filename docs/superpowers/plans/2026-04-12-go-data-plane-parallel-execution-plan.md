# Go Data Plane Parallel Execution Plan

This document defines how multiple workers can execute the rewrite in parallel
without overlapping heavily or creating hidden architecture drift.

## Execution Principles

- parallelize only after dependencies are explicit
- assign disjoint write scopes whenever possible
- keep shared files and root configs in small, intentional commits
- require a validation command and doc update for every slice
- report after each slice with what changed, what was validated, and what is
  still blocked

## Dependency Waves

### Wave 0: Documentation lock

This wave is complete when the current documentation set is accepted for the
branch.

### Wave 1: Contracts and bootstrap

Parallel work allowed:

- contract schemas and Buf setup
- Go module and service bootstrap
- telemetry and runtime scaffolding

Blocking output:

- frozen package list
- root Go subtree in place
- shared runtime conventions documented

### Wave 2: Scope and queue substrate

Parallel work allowed after Wave 1:

- scope and generation persistence
- fact and queue persistence
- storage adapters

Blocking output:

- bounded scope-generation lifecycle
- durable work-item model
- replay-safe state transitions

### Wave 3: Projector and reducer substrate

Parallel work allowed after Wave 2:

- source-local projector runtime
- reducer-intent scheduler
- reducer runtime skeleton
- canonical graph and content writers

Blocking output:

- projector writes are scope-local
- reducers own shared domains
- canonical write path is observable

### Wave 4: Proof migration and cutover

Parallel work allowed after Wave 3:

- proof-domain migration
- narrow compatibility bridge
- validation harnesses
- cutover documentation and retirement tasks

## Workstream Ownership

| Workstream | Dependencies | Owned paths | Done means |
| --- | --- | --- | --- |
| A. Contracts | docs locked | `proto/`, `buf*.yaml`, `go/gen/proto/` | schemas compile and version rules are documented |
| B. Runtime bootstrap | docs locked | `go/go.mod`, `go/cmd/`, `go/internal/app/`, `go/internal/runtime/`, `go/internal/telemetry/` | services boot with health, config, and telemetry shape |
| C. Scope lifecycle | A, B | `go/internal/scope/`, `schema/data-plane/postgres/`, `go/internal/storage/postgres/` | scopes and generations persist and transition correctly |
| D. Facts and queue | A, B | `go/internal/facts/`, `go/internal/queue/`, `go/internal/storage/postgres/` | bounded fact and work-item flow is durable |
| E. Projector runtime | C, D | `go/internal/projector/`, `go/internal/graph/`, `go/internal/content/` | source-local projection runs by scope generation |
| F. Reducer runtime | C, D | `go/internal/reducer/`, reducer-domain packages | reducer intents drain and write canonical shared truth |
| G. Compatibility bridge | E, F | `go/internal/compatibility/pythonbridge/` and minimal Python touch points | one proof domain can bridge safely during cutover |
| H. Validation and docs | every wave | tests, fixtures, runbooks, milestone docs | each slice has repeatable proof and updated docs |

## Coordination Rules

- Only one worker should own `buf*.yaml` or top-level generated code changes at
  a time.
- Storage schema and queue semantics changes should land before projector or
  reducer behavior that depends on them.
- Compatibility bridge work must stay behind the new contracts, not in front of
  them.
- Validation workers should not mask architecture gaps by hardcoding test-only
  behavior into production packages.

## Slice Reporting Template

Every slice report should answer:

- what paths were owned
- what contract or boundary changed
- what validation command passed
- what remains blocked and by which dependency wave
