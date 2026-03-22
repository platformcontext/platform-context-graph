# PlatformContextGraph Helm Chart

This chart deploys the combined PlatformContextGraph service with:

- external Neo4j connectivity
- bootstrap indexing via an internal Python runtime `initContainer`
- ongoing repo sync via an internal Python runtime sidecar
- flexible service exposure options

Render locally:

```bash
helm template platform-context-graph ./deploy/helm/platform-context-graph
```
