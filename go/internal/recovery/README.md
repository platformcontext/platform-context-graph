# Recovery

## Purpose

Operator-driven replay surface for the durable work queue. Lets admins reset
failed projector or reducer work items back to pending, or re-enqueue
projection for specific scopes without rebuilding the graph directly.

## Ownership boundary

Owns the replay and refinalize value contracts and the `Handler` that drives
them through a `ReplayStore`. The store is implemented in
`internal/storage/postgres`; this package never touches Postgres or the graph
backend itself.

## Exported surface

- `Stage` constants `StageProjector` and `StageReducer`.
- `ReplayFilter`, `ReplayResult`, `RefinalizeFilter`, `RefinalizeResult`
  with `Validate` methods.
- `ReplayStore` interface — the durable operations the handler needs.
- `Handler` plus `NewHandler`, `ReplayFailed`, and `Refinalize`.

## Dependencies

Standard library only. Storage adapters are injected via `ReplayStore`.

## Telemetry

This package emits no metrics, traces, or logs on its own. Replay store
implementations and the calling admin handler add the observability around
each call.

## Gotchas / invariants

- `ReplayFilter.Stage` must be `projector` or `reducer`; other values fail
  validation.
- `RefinalizeFilter.ScopeIDs` must be non-empty — refinalize is always scoped.
- `Handler.time()` returns UTC; callers should not assume local time when
  asserting against `now`.
- Recovery is queue replay, not direct graph mutation. Domains that consume
  reducer-derived state must still rely on the bootstrap-index ordering rules
  in `CLAUDE.md` after a replay.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/telemetry/index.md`
