# PlatformContextGraph Helm Chart

This chart deploys PlatformContextGraph as separate API and worker workloads with:

- external Neo4j connectivity
- a stateless API `Deployment` for HTTP API + MCP
- a stateful worker `StatefulSet` for repo sync and indexing
- flexible service exposure options

Render locally:

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph
```
