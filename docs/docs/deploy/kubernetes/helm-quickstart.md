# Helm quickstart

Use Helm when you want the supported split-service Kubernetes deployment.

## 1. Create the namespace

```bash
kubectl create namespace platform-context-graph
```

## 2. Create required secrets

The defaults expect:

- `pcg-api-auth` with key `api-key`
- `pcg-neo4j` with keys `username` and `password`
- `github-app-credentials` when `repoSync.auth.method=githubApp`

## 3. Write values

Start with a small override file:

```yaml
contentStore:
  dsn: postgresql://pcg:secret@postgres.platform.svc.cluster.local:5432/platform_context_graph

neo4j:
  uri: bolt://nornicdb.platform.svc.cluster.local:7687

env:
  PCG_GRAPH_BACKEND: nornicdb
  DEFAULT_DATABASE: nornic
  NEO4J_DATABASE: nornic

repoSync:
  source:
    mode: githubOrg
    githubOrg: platformcontext
    rules:
      - type: exact
        value: platformcontext/platform-context-graph
```

## 4. Install or upgrade

```bash
helm upgrade --install platform-context-graph ./deploy/helm/platform-context-graph \
  --namespace platform-context-graph \
  -f values.pcg.yaml
```

## 5. Check rollout

```bash
kubectl -n platform-context-graph get pods
kubectl -n platform-context-graph rollout status deployment/platform-context-graph
kubectl -n platform-context-graph rollout status deployment/platform-context-graph-mcp-server
kubectl -n platform-context-graph rollout status statefulset/platform-context-graph
kubectl -n platform-context-graph rollout status deployment/platform-context-graph-resolution-engine
```

Exact resource names depend on the release name and chart helpers. The API and
MCP workloads expose HTTP health endpoints through chart probes. Use logs,
metrics, and runtime status surfaces to diagnose ingester or resolution-engine
progress.
