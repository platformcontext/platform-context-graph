# Queue

## Purpose

Durable work-item contracts for the fact-projection queue. Models the row
shape, the lifecycle transitions, and the bounded retry and failure metadata
shared by projector and reducer consumers.

## Ownership boundary

Owns the work-item value type, status enum, transition methods, retry and
failure records, and the scope-generation key. Postgres-backed claim, lease,
and visibility logic lives in `internal/storage/postgres`. This package has
no I/O.

## Exported surface

- `WorkItem` value with `ScopeGenerationKey`.
- Transitions: `Claim`, `StartRunning`, `Retry`, `Fail`, `Succeed`, `Replay`.
- `WorkItemStatus` constants (`pending`, `claimed`, `running`, `retrying`,
  `succeeded`, `dead_letter`, and the deprecated `failed`).
- `RetryState` and `FailureRecord` carriers.

## Dependencies

Standard library only.

## Telemetry

None directly. Storage adapters and consumer workers add telemetry around
each transition.

## Gotchas / invariants

- Transitions return new values; the receiver is not mutated. Callers must
  persist the returned `WorkItem`.
- `Claim` requires a positive lease duration and a status of `pending` or
  `retrying`. Other statuses are not claimable.
- `Retry` requires a `nextAttempt` no earlier than `now`.
- `StatusFailed` is retained only so legacy rows can be replayed; new code
  should reach terminal failure via `Fail` (which writes `dead_letter`).
- `Replay` resets `AttemptCount` to zero. Operators using replay accept that
  retry budget restarts.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/deployment/service-runtimes.md`
- `go/internal/storage/postgres/` for the durable adapter
