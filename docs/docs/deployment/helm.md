# Helm Deployment

The Helm chart is the primary Kubernetes deployment artifact for PlatformContextGraph.

**Chart path:** `deploy/helm/platform-context-graph`

## Default Shape

The chart deploys two workloads:

- **API Deployment** — stateless, serves HTTP and MCP. Does not mount the repository workspace.
- **Ingester StatefulSet** — singleton, owns the shared workspace PVC, repository sync, and indexing lifecycle.

Both connect to external Neo4j and external Postgres.

## Install

```bash
helm install platform-context-graph ./deploy/helm/platform-context-graph
```

From the OCI registry:

```bash
helm install platform-context-graph oci://ghcr.io/platformcontext/charts/platform-context-graph
```

Render templates without installing:

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph
```

## Key Values

| Value | Purpose |
| :--- | :--- |
| `contentStore.dsn` | External PostgreSQL DSN for content search and cached source retrieval |
| `api.*` | API replica count and resource settings |
| `ingester.*` | Ingester replica count, PVC size, and resource settings |
| `repoSync.source.rules` | Structured include rules for Git discovery |
| `observability.otel.*` | OTLP settings for traces and metrics |
| `env.PCG_LOG_FORMAT` | Shared log format. Keep this at `json` in deployed environments. |

Typical OTEL collector override:

```yaml
env:
  PCG_LOG_FORMAT: json

observability:
  environment: ops-qa
  otel:
    enabled: true
    endpoint: http://otel-collector.monitoring.svc.cluster.local:4317
    protocol: grpc
    insecure: true
    tracesExporter: otlp
    metricsExporter: otlp
    logsExporter: none
```

The chart renders the same OTEL environment contract into both runtime workloads:

- the API `Deployment`
- the ingester `StatefulSet`, including bootstrap and repo-sync containers where applicable

It also sets a distinct `OTEL_SERVICE_NAME` per runtime so traces stay easy to split in Jaeger:

- `platform-context-graph-api`
- `platform-context-graph-ingester`

Typical override for a small deployment:

```yaml
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

contentStore:
  dsn: postgresql://pcg:secret@postgres:5432/pcg
```

## Exposure Modes

The chart defaults to `ClusterIP`. Four exposure options are available:

- `service.type=ClusterIP` (default)
- `service.type=LoadBalancer`
- `exposure.ingress.enabled=true`
- `exposure.gateway.enabled=true` (Gateway API HTTPRoute)

Do not enable both ingress and gateway at the same time.

## Repository Rules

The ingester discovers and filters repositories using structured rules. Rules match against normalized `org/repo` identifiers and support both exact and regex patterns.

```yaml
repoSync:
  source:
    rules:
      - exact: platformcontext/platform-context-graph
      - regex: platformcontext/(payments|orders)-.*
```

The chart renders these into `PCG_REPOSITORY_RULES_JSON`.

On each sync cycle the ingester:

1. Re-evaluates the configured rules against available repositories
2. Clones or updates matching repositories
3. Re-indexes the workspace
4. Reports stale checkouts (repos that no longer match) in metrics and logs — but does not delete them automatically

## Postgres Requirements

The external PostgreSQL instance must support the `pg_trgm` extension. PCG creates trigram indexes for file and entity content search.

## Logging And Tracing Defaults

Production should keep two observability defaults in place:

- `PCG_LOG_FORMAT=json`
- OTLP trace export enabled through the existing `observability.otel.*` values

That gives you:

- newline-delimited JSON logs on stdout for log shipping
- OTEL traces for Jaeger and other trace backends
- shared request and trace correlation fields across API, MCP, and ingester logs

PCG does not require the OTEL logs signal. The intended deployment shape is JSON stdout for logs and OTLP for traces.

Use Jaeger when you need to answer a performance question. The trace tells you where time went; the JSON logs fill in the repo, batch, and request details around that span.
