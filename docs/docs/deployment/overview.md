# Deployment Overview

PlatformContextGraph can be run locally or as a networked service, but the public deployment contract is opinionated:

- **external Neo4j**
- **external Postgres for indexed content retrieval and search**
- **bootstrap indexing before serving traffic**
- **repo sync and re-index as part of the runtime**
- **one deployment that can expose HTTP API and MCP**

## Choose a deployment path

### Minimal manifests

Use [Minimal Manifests](manifests.md) when you want the smallest possible Kubernetes example and you are comfortable managing details yourself.

### Helm

Use [Helm](helm.md) when you want the real deployment path for Kubernetes, EKS, or GitOps environments.

### Docker Compose

Use [Docker Compose](docker-compose.md) for local end-to-end testing with Neo4j, bootstrap indexing, and the combined service.

### Argo CD

Use [Argo CD](argocd.md) when you want GitOps-managed deployment with the public chart and example overlays.

## Production shape

The chart and deployable-service story assume:

- a `StatefulSet`
- attached workspace storage
- a bootstrap indexing `initContainer`
- a long-running repo-sync sidecar
- external Neo4j credentials provided through environment or secret management
- external Postgres credentials provided through environment or secret management

The repo-sync sidecar is responsible for ongoing rediscovery:

- it re-evaluates the configured repository source on each sync cycle
- when `repositoryRules` are configured, it applies exact and regex filters against normalized `org/repo` identifiers
- it re-indexes the shared workspace when repositories were cloned or updated
- it reports stale local checkouts that no longer match current discovery, but does not remove them automatically

## What this replaces

Older Docker-only setup guides and generic hosting comparisons have been removed from the public docs because they no longer describe the current release story accurately.
