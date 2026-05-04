# Coordinator

## Purpose

Runs the workflow coordinator service: declarative collector-instance
reconciliation, expired-claim reaping, and workflow-run progress
reconciliation. Owns the runtime loop; the durable store and the workflow
contracts live elsewhere.

## Ownership boundary

Owns reconcile/reap loop scheduling, OTEL instrument registration for the
coordinator, and `PCG_WORKFLOW_COORDINATOR_*` env parsing. Durable mutations
are delegated to a `Store` implementation backed by `internal/storage/postgres`
through the `internal/workflow` contracts.

## Exported surface

- `Config`, `LoadConfig`, and `Validate` for env-driven configuration.
- `Service` and `Service.Run` for the long-running coordinator loop.
- `Store` interface — the narrow store surface needed by the loop.
- `Metrics`, `NewMetrics`, and the `ReconcileObservation`,
  `ReapObservation`, `RunReconciliationObservation` value types.

## Dependencies

- `internal/workflow` for desired/durable collector instances, claims, and
  contracts.
- `internal/scope` for collector kinds.
- `internal/telemetry` for metric dimension keys.

## Telemetry

OTEL meters registered against the `pcg_dp_workflow_coordinator_` prefix:

- `reconcile_total`, `reconcile_duration_seconds`
- `reap_total`, `reap_duration_seconds`
- `run_reconcile_total`, `run_reconcile_duration_seconds`
- Observable gauges: `desired_collector_instances`,
  `durable_collector_instances`, `collector_instance_drift`,
  `last_reaped_claims`, `last_reconciled_runs`

The service emits a `slog` info line on first run reporting deployment mode and
loop intervals, plus warnings on observed collector drift.

## Gotchas / invariants

- `Config.Validate` runs at load and on each `Run`; defaults backfill at most
  before validation, so omitting an env var is fine but a malformed value
  fails fast.
- Active mode without `claims_enabled` and at least one enabled
  claim-capable collector instance fails validation.
- `HeartbeatInterval` must be strictly less than `ClaimLeaseTTL`.
- Reap and run reconciliation only run in active mode; the reap ticker is nil
  in dark mode and the loop's `select` skips it via `tickerChan(nil)`.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/telemetry/index.md`
