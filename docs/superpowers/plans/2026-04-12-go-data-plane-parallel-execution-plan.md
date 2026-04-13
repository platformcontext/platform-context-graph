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

## Milestone Summary

| Milestone | Primary outcome | Effort | Sequencing dependency | Validation expectation |
| --- | --- | --- | --- | --- |
| 0 | Lock contracts and documentation | Small | start here | docs build, contract freeze, no open design gaps |
| 1 | Native Git cutover and operability | Large | milestone 0 | local runtime proof, admin/status visibility, Git path tests |
| 2 | Scope-first ingestion | Large | milestone 1 substrate | scope/generation lifecycle, replay-safe incremental refresh |
| 3 | Canonical truth layers | Large | milestone 2 substrate | cross-source correlation and layered truth tests |
| 4 | Legacy write-path retirement | Medium | milestone 1-3 proof | bridge regression tests and no new logic on the old seam |
| 5 | Multi-collector expansion | Large | milestone 4 authority flip | AWS/Kubernetes collector proof and end-to-end scale checks |

## Workstream Ownership

| Workstream | Dependencies | Owned paths | Effort | Done means | Validation |
| --- | --- | --- | --- | --- | --- |
| A. Contracts | docs locked | `proto/`, `buf*.yaml`, `go/gen/proto/` | Medium | schemas compile and version rules are documented | contract tests and docs build |
| B. Runtime bootstrap | docs locked | `go/go.mod`, `go/cmd/`, `go/internal/app/`, `go/internal/runtime/`, `go/internal/telemetry/` | Large | services boot with health, config, and telemetry shape | service bootstrap and runtime tests |
| C. Scope lifecycle | A, B | `go/internal/scope/`, `schema/data-plane/postgres/`, `go/internal/storage/postgres/` | Large | scopes and generations persist and transition correctly | scope lifecycle and replay tests |
| D. Facts and queue | A, B | `go/internal/facts/`, `go/internal/queue/`, `go/internal/storage/postgres/` | Large | bounded fact and work-item flow is durable | fact/queue persistence tests |
| E. Projector runtime | C, D | `go/internal/projector/`, `go/internal/graph/`, `go/internal/content/` | Large | source-local projection runs by scope generation | projector integration tests |
| F. Reducer runtime | C, D | `go/internal/reducer/`, reducer-domain packages | Large | reducer intents drain and write canonical shared truth | reducer integration and replay tests |
| G. Compatibility bridge | E, F | `go/internal/compatibility/pythonbridge/` and minimal Python touch points | Medium | one proof domain can bridge safely during cutover | bridge regression and proof-domain tests |
| H. Validation and docs | every wave | tests, fixtures, runbooks, milestone docs | Medium | each slice has repeatable proof and updated docs | docs build plus targeted validation commands |

## Coordination Rules

- Only one worker should own `buf*.yaml` or top-level generated code changes at
  a time.
- Storage schema and queue semantics changes should land before projector or
  reducer behavior that depends on them.
- Compatibility bridge work must stay behind the new contracts, not in front of
  them.
- Validation workers should not mask architecture gaps by hardcoding test-only
  behavior into production packages.
- Every slice should report which milestone it advances, which validation gate
  it satisfied, and whether the change is final or a temporary bridge.

## Slice Reporting Template

Every slice report should answer:

- what paths were owned
- what contract or boundary changed
- what validation command passed
- what remains blocked and by which dependency wave
