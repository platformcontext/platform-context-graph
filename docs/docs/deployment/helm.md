# Helm Deployment

The Helm chart is the primary Kubernetes deployment artifact for PlatformContextGraph.

Chart path:
- `deploy/helm/platform-context-graph`

Default deployment shape:
- stateless API `Deployment`
- singleton repository ingester `StatefulSet`
- external Neo4j
- external Postgres for indexed content search and cached source retrieval
- API serves HTTP and MCP without mounting the repository workspace PVC
- the ingester owns the shared workspace PVC, repository sync, and indexing lifecycle
- `ClusterIP` service by default

Supported exposure modes:
- `service.type=ClusterIP`
- `service.type=LoadBalancer`
- `exposure.ingress.enabled=true`
- `exposure.gateway.enabled=true`

Do not enable both ingress and gateway exposure at the same time.

Example install:

```bash
helm install platform-context-graph ./deploy/helm/platform-context-graph
```

Example render:

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph
```

Important values:

- `contentStore.dsn`: external PostgreSQL DSN used for content search and cached source retrieval
- `api.*`: API replica and resource settings
- `ingester.*`: ingester replica, PVC, and resource settings
- `repoSync.source.rules`: structured include rules for Git discovery
- `observability.otel.*`: OTLP settings for traces and metrics

Repository rules support mixed exact and regex matching against normalized `org/repo` identifiers. The chart renders them into `PCG_REPOSITORY_RULES_JSON`.

The external PostgreSQL instance must support the `pg_trgm` extension, because PCG creates trigram indexes for file and entity content search.

The repository ingester re-discovers repositories on every sync cycle using those rules:

- matching repositories are cloned or updated and then included in the next re-index
- repositories that no longer match the current discovery result are counted as stale checkouts
- stale checkouts are reported in runtime metrics and logs, but the runtime does not delete them automatically

Example `repoSync.source.rules` value:

```yaml
repoSync:
  source:
    rules:
      - exact: platformcontext/platform-context-graph
      - regex: platformcontext/(payments|orders)-.*
```
