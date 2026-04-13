# Cloud Validation Runbook

Use this companion runbook when validating a hosted or Kubernetes deployment.
It is the cloud-side pair for [Local Testing Runbook](local-testing.md).

## What To Prove

Treat the runtime health checks and the completeness checks as different
questions:

- `health` or `healthz` proves the process is alive and initialized
- `index-status` proves a run or repository checkpoint completed
- `/admin/status` proves the live runtime stage, backlog, and failure state
  when the runtime mounts the shared admin surface

Do not stop at pod health when the goal is operator confidence in freshness.

## Minimum Validation Order

1. Check the runtime health signal for the service you are validating.
2. Check `pcg index-status --profile <profile>` or the hosted
   `/api/v0/index-status` route for checkpointed completeness.
3. If you need a run-specific view, inspect `/api/v0/index-runs/{run_id}` and
   `/api/v0/index-runs/{run_id}/coverage`.
4. If you are debugging a recovery action, inspect
   `/api/v0/admin/refinalize/status`.

## Useful Hosted Checks

```bash
pcg index-status --profile qa
pcg index-status run-123 --profile qa
curl -fsS https://pcg.example.com/api/v0/index-status
curl -fsS https://pcg.example.com/api/v0/index-runs/run-123
curl -fsS https://pcg.example.com/api/v0/index-runs/run-123/coverage
curl -fsS https://pcg.example.com/api/v0/admin/refinalize/status
```

## Kubernetes Logs

When completeness and health diverge, inspect the live pod logs next:

```bash
kubectl logs -n platform-context-graph deployment/platform-context-graph-api --tail=50
kubectl logs -n platform-context-graph statefulset/platform-context-graph-ingester --tail=50
kubectl logs -n platform-context-graph deployment/platform-context-graph-resolution-engine --tail=50
```

Use the API logs for status lookups and admin calls, the ingester logs for
sync and checkpoint progress, and the resolution-engine logs for queue draining
and projection recovery.

## Refinalize Boundary

The hosted `POST /api/v0/admin/refinalize` route is graph-safe only. It
supports the rewritten graph-stage recovery path and keeps file-dependent
bridge stages out of the API. If you need the legacy file-dependent bridge,
use the CLI-only local recovery path until the Go-owned replacement exists.

## When To Stop

You are done when:

- the health check is green
- `index-status` reports the expected checkpointed state
- the run-specific coverage rows match the expected remaining gaps
- `admin/refinalize/status` is idle or complete for the recovery flow you ran
