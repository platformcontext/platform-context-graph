# Deployment Overview

PlatformContextGraph supports both a local full-stack workflow and a deployed
split-service workflow. The current runtime surface includes four long-running
Go runtimes:

- **API** for HTTP query traffic
- **MCP Server** for MCP transport
- **Ingester** for repository sync, parsing, and fact emission
- **Resolution Engine** for queued projection and recovery workflows

The currently packaged Helm and Argo CD deployment docs focus on API,
ingester, and resolution-engine. The MCP server is also implemented as a
separate Go runtime and is available in local Compose.

Both the ingester and resolution-engine use the same facts-first data flow and
write into external Neo4j and external Postgres.

## Choose A Deployment Path

| Path | Best for | What you get |
| --- | --- | --- |
| [Docker Compose](docker-compose.md) | local full-stack testing | Neo4j, Postgres, OTEL collector, Jaeger, bootstrap-index, API, MCP server, ingester, and resolution-engine |
| [Helm](helm.md) | supported Kubernetes deployment | split API, ingester, and resolution-engine workloads with optional ServiceMonitor support; MCP is a separate Go runtime surface |
| [Argo CD](argocd.md) | GitOps-managed Kubernetes deployment | Helm-based deployment through GitOps overlays |
| [Minimal Manifests](manifests.md) | smallest raw manifest example | a single-runtime API example, not the full split-service production shape |

## Deployed Runtime Flow

```mermaid
flowchart LR
  A["Ingester"] --> B["Parse repository snapshot"]
  B --> C["Postgres fact store"]
  C --> D["Fact work queue"]
  D --> E["Resolution Engine"]
  E --> F["Neo4j graph"]
  E --> G["Postgres content store"]
  H["API"] --> F
  H --> G
  I["MCP Server"] --> F
  I --> G
```

## Platform Differences

| Surface | Docker Compose | Helm / Argo CD | Minimal Manifests |
| --- | --- | --- | --- |
| Runtime shape | full local stack | supported production shape | single-runtime example |
| API | yes | yes | yes |
| MCP Server | yes | separate runtime surface | no |
| Ingester | yes | yes | no |
| Resolution Engine | yes | yes | no |
| Bootstrap Index | yes, one-shot service | manual or operator-run activity | no |
| Shared repo workspace | bind-mounted local fixture or host path | ingester-only PVC | statefulset-local only |
| Direct `/metrics` ports | yes | optional | not packaged |
| Kubernetes `ServiceMonitor` | no | optional | no |

## Production Defaults

The intended production shape assumes:

- external Neo4j
- external Postgres
- attached workspace storage only on the ingester
- API and resolution-engine remaining stateless
- OTLP and JSON-log observability enabled
- optional direct scrape endpoints and `ServiceMonitor` resources per runtime

Use [Service Runtimes](service-runtimes.md) for the operator contract and
[Helm](helm.md) for the exact deployment values.
