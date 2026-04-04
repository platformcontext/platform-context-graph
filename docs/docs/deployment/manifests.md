# Minimal Manifests

`deploy/manifests/minimal` is the smallest raw Kubernetes example in the
repository. It is useful when you want to inspect the API runtime contract
without bringing in the full Helm deployment.

## What It Is

- one namespace
- one config map
- one external Neo4j secret example
- one API-serving `StatefulSet`
- one `ClusterIP` service

## What It Is Not

This example is **not** the full split-service production shape.

It does **not** include:

- the ingester runtime
- the resolution-engine runtime
- the facts-first queue-backed deployment flow
- Prometheus `ServiceMonitor` resources

If you want the supported multi-service Kubernetes deployment, use
[Helm](helm.md) instead.

## Apply It

```bash
kubectl apply -k deploy/manifests/minimal
```

## When To Choose It

Choose this path when you want:

- a minimal API example for local Kubernetes experiments
- a compact starting point for understanding the service contract
- the least amount of Kubernetes machinery before moving to Helm or Argo CD
