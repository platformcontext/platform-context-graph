# Upgrade and rollback

Treat PCG upgrades like data-plane changes. The application image, Postgres
schema, graph schema, and worker behavior move together.

## Before upgrade

1. Pin the target image tag in values.
2. Render the chart with the same values used by the cluster.
3. Review changes to workloads, environment variables, probes, security
   contexts, PVCs, and ServiceMonitors.
4. Confirm Postgres and graph backups are recent enough for the rollout risk.
5. Check current queue depth, queue age, dead-letter state, and indexing
   completeness.

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph \
  --namespace platform-context-graph \
  -f values.pcg.yaml
```

## Upgrade

```bash
helm upgrade platform-context-graph ./deploy/helm/platform-context-graph \
  --namespace platform-context-graph \
  -f values.pcg.yaml
```

Watch the rollout with `kubectl get pods` and `kubectl rollout status` for the
API, MCP, ingester, and resolution-engine workloads.

## Rollback

```bash
helm history platform-context-graph --namespace platform-context-graph
helm rollback platform-context-graph <revision> --namespace platform-context-graph
```

Rollback does not replace a database restore plan. If an upgrade changes durable
state in a way that the older image cannot read, restore Postgres and graph
state according to your platform backup runbook.
