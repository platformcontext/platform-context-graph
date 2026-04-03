# Deployment Overview

PlatformContextGraph can be run locally or as a networked service, but the public deployment contract is opinionated:

- **external Neo4j**
- **external Postgres for indexed content retrieval and search**
- **stateless API runtime for HTTP and MCP**
- **stateful repository ingester runtime for sync and indexing**
- **standalone resolution-engine runtime for queued fact projection**
- **API can serve before ingestion catches up**

## Choose a deployment path

### Minimal manifests

Use [Minimal Manifests](manifests.md) when you want the smallest possible Kubernetes example and you are comfortable managing details yourself.

### Helm

Use [Helm](helm.md) when you want the real deployment path for Kubernetes, EKS, or GitOps environments.

### Docker Compose

Use [Docker Compose](docker-compose.md) for local end-to-end testing with Neo4j, bootstrap indexing, API, repo-sync, and the standalone resolution-engine runtime.

### Argo CD

Use [Argo CD](argocd.md) when you want GitOps-managed deployment with the public chart and example overlays.

## Production shape

The chart and deployable-service story assume:

- an API `Deployment`
- a Resolution Engine `Deployment`
- a repository ingester `StatefulSet`
- attached workspace storage only on the ingester
- external Neo4j credentials provided through environment or secret management
- external Postgres credentials provided through environment or secret management

Use [Service Runtimes](service-runtimes.md) when you need the operator view of
what each runtime does, how it starts, and which workload should be tuned or
scaled first.

The repository ingester is responsible for ongoing rediscovery:

- it re-evaluates the configured repository source on each sync cycle
- when `repositoryRules` are configured, it applies exact and regex filters against normalized `org/repo` identifiers
- it re-indexes the shared workspace when repositories were cloned or updated
- it reports stale local checkouts that no longer match current discovery, but does not remove them automatically
