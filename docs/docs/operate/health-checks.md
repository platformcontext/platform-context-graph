# Health Checks

Health checks answer three different questions. Keep them separate.

| Question | Signal |
| --- | --- |
| Is the process alive and initialized? | `/healthz`, `/readyz`, or MCP `GET /health` |
| Is the runtime stuck, failing, or behind? | `/admin/status` on the relevant runtime |
| Is indexed data complete enough for the question? | `GET /api/v0/index-status`, `GET /api/v0/status/index`, or repository coverage |

A green process health check does not mean indexing finished.

## Runtime Endpoints

Long-running Go runtimes that mount the shared admin surface expose:

- `GET /healthz`
- `GET /readyz`
- `GET /admin/status`
- `GET /metrics` when a metrics handler is mounted

The MCP server also exposes `GET /health`, `GET /sse`, and
`POST /mcp/message`.

Use [Runtime Admin API](../reference/runtime-admin-api.md) for the exact
contract.

## Local Compose Checks

```bash
curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz
curl -fsS http://localhost:8080/admin/status
curl -fsS http://localhost:8081/health
curl -fsS http://localhost:8080/api/v0/index-status
```

Metrics endpoints are exposed directly by service:

- API: `http://localhost:19464/metrics`
- Ingester: `http://localhost:19465/metrics`
- Resolution Engine: `http://localhost:19466/metrics`
- MCP: `http://localhost:19468/metrics`

## Kubernetes Checks

```bash
kubectl get pods -n platform-context-graph
kubectl get services -n platform-context-graph
kubectl logs -n platform-context-graph deployment/platform-context-graph --tail=50
kubectl logs -n platform-context-graph statefulset/platform-context-graph-ingester --tail=50
kubectl logs -n platform-context-graph deployment/platform-context-graph-resolution-engine --tail=50
```

If API and MCP are healthy but answers are stale, check ingestion, queue drain,
Postgres, and graph projection next.
