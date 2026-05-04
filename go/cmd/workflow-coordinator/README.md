# workflow-coordinator

## Purpose

`pcg-workflow-coordinator` reconciles the declarative set of collector
instances against `WorkflowControlStore` and, in active mode, reaps expired
work-item claims and recomputes workflow-run state. It exposes the shared
admin/status contract during its dark rollout so operators can validate
the control plane before active mode is enabled. Trigger normalization and
permanent claim ownership are not part of this binary today; the truth they
will eventually publish is still owned by other components.

## Ownership boundary

The binary wires `coordinator.Service` against `WorkflowControlStore`,
coordinator metrics, and the shared logger. It does not own canonical
graph reconciliation, reducer-owned convergence truth, repository sync,
or parsing. Permanent production claim ownership is blocked while the
runtime runs in `dark` mode.

## Entry points

- `main` and `run` in `go/cmd/workflow-coordinator/main.go`
- service definition lives in `internal/coordinator/`

## Configuration

Loaded via `coordinator.LoadConfig(getenv)`:

- `PCG_WORKFLOW_COORDINATOR_DEPLOYMENT_MODE` — `dark` (default) or active
- `PCG_WORKFLOW_COORDINATOR_CLAIMS_ENABLED` — must be `true` for active
  claim ownership; default `false`
- standard Postgres env via `runtime.OpenPostgres`

Compose exposes the optional metrics port `19469`. Helm keeps
`workflowCoordinator.enabled=false`, `deploymentMode=dark`, and
`claimsEnabled=false` in this branch.

## Telemetry

Uses `telemetry.NewBootstrap("workflow-coordinator")` and
`NewProviders`. Logger scope `workflow-coordinator`/component
`workflow-coordinator`. Domain metrics are created by
`coordinator.NewMetrics(meter)` in `internal/coordinator`. The shared
`/metrics`, `/healthz`, `/readyz`, `/admin/status` admin surface is
mounted by `app.NewHostedWithStatusServer`; see
`internal/runtime/README.md`.

## Gotchas / invariants

- dark by default: active claim ownership requires the deployment-mode
  and claims-enabled flags plus an explicit claim-enabled collector
  instance in Compose
- the coordinator does not reconcile canonical graph truth; treat it as
  a control plane on top of `pcg-reducer`
- shutdown is signal-driven (`SIGINT`/`SIGTERM`)

## Related docs

- [Service runtimes — Workflow Coordinator](../../../docs/docs/deployment/service-runtimes.md#workflow-coordinator)
- [Helm deployment](../../../docs/docs/deployment/helm.md)
- [Docker Compose deployment](../../../docs/docs/deployment/docker-compose.md)
