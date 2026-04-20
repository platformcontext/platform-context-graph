# PlatformContextGraph Helm Chart

This chart deploys PlatformContextGraph as separate API, MCP, ingester,
workflow-coordinator, and resolution-engine workloads with:

- External Neo4j and Postgres connectivity
- A short-lived `pcg-bootstrap-data-plane` init container on every database-backed workload
- A stateless API `Deployment` for HTTP API
- A stateless MCP `Deployment` for MCP transport and mounted query routes
- A stateful repository ingester `StatefulSet` for repo sync and indexing
- An optional workflow-coordinator `Deployment` for dark-mode control-plane validation
- A stateless Resolution Engine `Deployment` for facts queue projection
- Optional Prometheus scrape endpoints and `ServiceMonitor` resources for API, MCP, ingester, workflow-coordinator, and resolution-engine
- Flexible service exposure (ClusterIP, LoadBalancer, Ingress, Gateway API)
- Hardened defaults such as public API docs disabled unless explicitly re-enabled

## Render locally

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph
```

## Typical value overrides

```yaml
contentStore:
  dsn: postgresql://pcg:secret@postgres:5432/pcg

apiAuth:
  secretName: pcg-api-auth
  key: api-key

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
  connectionTuning:
    postgres:
      maxOpenConns: "40"
      pingTimeout: 15s
    neo4j:
      connectionAcquisitionTimeout: 20s

resolutionEngine:
  connectionTuning:
    neo4j:
      maxConnectionPoolSize: "150"

repoSync:
  source:
    rules:
      - exact: myorg/my-repo
      - regex: myorg/platform-.*

env:
  PCG_ENABLE_PUBLIC_DOCS: "true"

observability:
  environment: dev
  otel:
    enabled: true
    endpoint: http://otel-collector.monitoring.svc.cluster.local:4317
    protocol: grpc
    insecure: true
    tracesExporter: otlp
    metricsExporter: otlp
    logsExporter: none
  prometheus:
    enabled: true
    serviceMonitor:
      enabled: true
```

See [docs/docs/deployment/helm.md](../../../docs/docs/deployment/helm.md) for the full deployment guide.
