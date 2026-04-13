# Milestone 2: Scope-First Ingestion And Incremental Refresh

This document is the execution plan for the second rewrite milestone.

Milestone 2 starts from the completed Milestone 1 substrate:

- Go-owned collector orchestration and fact commit
- live projector and reducer runtime proofs
- shared admin, health, readiness, and metrics contract
- narrowed transitional Python adapters only where parser/discovery logic still
  remains outside Go

## Summary

Milestone 2 moves PCG from a bounded Git proof path to a durable
scope-first ingestion model that supports incremental refresh without requiring
platform-wide re-indexes.

The goal is not “more collectors” yet.

The goal is to make the ingestion contract correct enough that AWS,
Kubernetes, SQL, and future source families can land on the same substrate
without bending everything back into repository-shaped assumptions.

## Completion Standard

Milestone 2 is complete only when all of the following are true:

- scope identity and generation replacement work as first-class durable
  concepts rather than repo-shaped approximations
- collector and queue state can explain what changed at the scope boundary
- stale generations can be replaced or superseded without full-platform
  re-indexes
- replay, delete, and retraction semantics are correct for authoritative
  snapshots
- at least one repo-backed source proves incremental refresh on the new model

## Workstreams

### Workstream A: Scope Lifecycle Contract

Purpose:
Make scope and generation lifecycle explicit enough for non-Git collectors.

Owned paths:

- `go/internal/scope/`
- `go/internal/storage/postgres/ingestion.go`
- `go/internal/storage/postgres/schema.go`
- scope lifecycle docs and ADR references

Deliverables:

- explicit generation replacement and supersession semantics
- durable status transitions for pending, active, superseded, and replayed
  generations
- queryable scope hierarchy support for parent/child boundaries

Effort:

- `Large`

### Workstream B: Incremental Refresh And Reconciliation

Purpose:
Refresh only changed scopes and generations instead of falling back to broad
re-index behavior.

Owned paths:

- `go/internal/collector/`
- `go/internal/storage/postgres/`
- `go/internal/projector/`
- replay and refresh proof harnesses

Deliverables:

- changed-scope refresh path for the bounded Git source
- authoritative snapshot replacement flow
- stale generation handling and replay-safe work scheduling

Effort:

- `Large`

### Workstream C: Scope-Aware Status, Telemetry, And Admin

Purpose:
Expose incremental ingestion honestly to operators and future automation.

Owned paths:

- `go/internal/status/`
- `go/internal/runtime/`
- `go/internal/telemetry/`
- `go/cmd/admin-status/`
- runtime docs and local runbooks

Deliverables:

- status views that explain changed scopes, active generations, and superseded
  generations
- metrics for scope churn, generation replacement, queue age, and replay volume
- clear operator story for “what changed” versus “what is fully healthy”

Effort:

- `Medium`

### Workstream D: Proof Harnesses And Regression Gates

Purpose:
Make scope-first incremental refresh locally provable before AWS or Kubernetes
collector work begins.

Owned paths:

- Go unit and integration tests
- Python compatibility tests that still matter during the transition
- compose-backed proof scripts
- milestone validation docs

Deliverables:

- deterministic tests for generation replacement and stale-generation cleanup
- one live compose proof for incremental refresh on a repo-backed source
- a stronger compose gate that starts from one active generation, proves an
  unchanged rerun leaves the authoritative generation and projector queue
  untouched, and then proves a changed rerun can be forced into a single
  runtime-generated `retrying` state before the active/superseded swap
  completes
- replay and retraction regression coverage

Effort:

- `Medium`

## Suggested Agent Split

Use four workers plus one integrator.

- Worker 1:
  Scope lifecycle contract and schema semantics
- Worker 2:
  Incremental refresh collector/projector/reducer behavior
- Worker 3:
  Status, telemetry, metrics, and admin visibility
- Worker 4:
  Proof harnesses, regression gates, and doc/runbook updates
- Main agent:
  architecture decisions, integration, verification, and backlog management

## First Wave

Wave 1 should start with these larger chunks, not micro-slices:

1. lock the generation replacement state machine and schema semantics
2. implement one repo-backed incremental refresh flow end to end
3. add scope-aware status and metrics so operators can inspect the new model
4. add deterministic proof gates for replacement, replay, and stale cleanup

## Validation Gate

Milestone 2 should not be called complete without:

```bash
cd go
go test ./internal/scope ./internal/collector ./internal/projector \
  ./internal/reducer ./internal/storage/postgres ./internal/runtime \
  ./internal/telemetry -count=1
```

```bash
./scripts/verify_collector_git_runtime_compose.sh
./scripts/verify_projector_runtime_compose.sh
./scripts/verify_reducer_runtime_compose.sh
./scripts/verify_incremental_refresh_compose.sh
```

The incremental-refresh proof is currently blocked by the projector handoff
ordering around `scope_generations_active_scope_idx`; keep that blocker
visible until the changed rerun can swap generations cleanly. The new retryable
proof shape is intentionally aligned to the runtime marking a projector work
item `retrying` once through the live retry-once env var before it gets
reclaimed; if the live stack cannot emit that state itself, call that out
explicitly instead of pretending the retry loop is automatic.
