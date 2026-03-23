# PlatformContextGraph Helm Chart

This chart deploys PlatformContextGraph as separate API and ingester workloads with:

- External Neo4j and Postgres connectivity
- A stateless API `Deployment` for HTTP API + MCP
- A stateful repository ingester `StatefulSet` for repo sync and indexing
- Flexible service exposure (ClusterIP, LoadBalancer, Ingress, Gateway API)

## Render locally

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph
```

## Typical value overrides

```yaml
contentStore:
  dsn: postgresql://pcg:secret@postgres:5432/pcg

api:
  replicas: 2
  resources:
    requests:
      cpu: 250m
      memory: 512Mi

ingester:
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
  persistence:
    size: 20Gi

repoSync:
  source:
    rules:
      - exact: myorg/my-repo
      - regex: myorg/platform-.*
```

See [docs/docs/deployment/helm.md](../../../docs/docs/deployment/helm.md) for the full deployment guide.
