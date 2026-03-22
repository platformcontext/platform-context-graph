# Prerequisites

Before you install PlatformContextGraph, decide which mode you want first:

- **Local CLI and MCP** for single-user development workflows
- **HTTP API + MCP service** for automation or team-shared usage
- **Kubernetes deployment** when you want bootstrap indexing, repo sync, and a long-running service

## What PCG needs

### Python runtime

- Python 3.10 or newer
- `uv`, `pipx`, or `pip` available for installation

### Graph database

PCG can run locally, but the production and deployable-service path assumes **external Neo4j**.

| Backend | Best fit | Notes |
| --- | --- | --- |
| FalkorDB Lite | local experimentation on supported platforms | Useful for lightweight local workflows, but not the production deployment contract |
| Neo4j | shared usage, Kubernetes, production, large graphs | Canonical backend for the deployable service path |

### Optional infrastructure tooling

- Docker Desktop or Docker Engine for local service testing
- Kubernetes and Helm for cluster deployments
- Argo CD for GitOps-style deployments

## Platform notes

- **macOS / Linux:** local CLI and MCP setup is straightforward.
- **Windows:** use [Windows Setup](windows-setup.md) if you need WSL guidance or Neo4j-specific setup help.
- **Kubernetes:** the public chart assumes external Neo4j and a persistent workspace volume for bootstrap indexing and repo sync.

## Before your first index

Make sure you know:

- which repository or mono-folder you want to index first
- whether you want code-only indexing or code plus infrastructure context
- whether you want to run over stdio MCP or expose the HTTP API as a service
