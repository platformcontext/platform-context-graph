# PlatformContextGraph

**A deployable, Kubernetes-native context graph that connects code to cloud infrastructure.**

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/platformcontext/platform-context-graph?style=flat-square" alt="License">
  </a>
  <a href="https://github.com/platformcontext/platform-context-graph/actions/workflows/test.yml">
    <img src="https://github.com/platformcontext/platform-context-graph/actions/workflows/test.yml/badge.svg" alt="Tests">
  </a>
  <a href="docs/">
    <img src="https://img.shields.io/badge/docs-MkDocs-blue?style=flat-square" alt="Docs">
  </a>
  <img src="https://img.shields.io/badge/MCP-Compatible-green?style=flat-square" alt="MCP Compatible">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/ghcr.io-image-2496ED?style=flat-square&logo=docker&logoColor=white" alt="GHCR Image">
  <img src="https://img.shields.io/badge/helm-OCI-0F1689?style=flat-square&logo=helm&logoColor=white" alt="Helm OCI Chart">
</p>

## What is this

PlatformContextGraph started as a fork of [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext), which builds a graph of source code relationships for AI-assisted development. That was a good starting point, but we needed more.

We needed the graph to understand infrastructure — Terraform modules, Helm charts, Kubernetes manifests, ArgoCD Applications, Crossplane XRDs, CloudFormation stacks. We needed to trace from a running workload back to the repo and code that defines it. We needed it to run on the network as a service, not just on a developer's laptop. And we needed it deployable to Kubernetes with proper separation of API and ingester workloads.

So we rebuilt it into that.

## What we built that's new

**IaC-native graph** — First-class parsers for Terraform/HCL, Kubernetes manifests, ArgoCD Applications and ApplicationSets, Crossplane XRDs, CloudFormation, Helm, and Kustomize. Infrastructure is a first-class citizen in the graph, not an afterthought.

**Bidirectional tracing** — Trace from a cloud resource back to the repo and code that defines it, or from code forward to what it deploys. `trace_resource_to_code`, `trace_deployment_chain`, `explain_dependency_path`.

**Blast radius and change surface** — Before you merge, see what breaks. Transitive dependency analysis across repos and infrastructure boundaries.

**Deployable service architecture** — Stateless API Deployment + stateful Ingester StatefulSet. Neo4j for the graph, Postgres for portable content retrieval. Helm chart, Kustomize manifests, and ArgoCD overlays included.

**Portable content model** — Queries return `repo_id + relative_path`, not server filesystem paths. The Postgres content store means the API serves source code without needing the repo checked out locally.

**Three interfaces, one query model** — CLI for local dev, MCP for AI assistants, HTTP API for automation. Same capabilities everywhere.

**Multi-repo ecosystem indexing** — Index entire orgs. Cross-repo dependency resolution. Environment comparison across prod, staging, and dev.

**30+ language parsers** — Python, Go, TypeScript, Java, Rust, C/C++, and more via tree-sitter.

## Quick Start

Install the CLI tool:

```bash
uv tool install platform-context-graph
```

Or run from source:

```bash
uv sync
uv run pcg --help
```

Index a repository:

```bash
pcg index .
```

Run a query:

```bash
pcg analyze callers process_payment
```

Start MCP:

```bash
pcg mcp start
```

Start the combined HTTP API + MCP service:

```bash
pcg serve start --host 0.0.0.0 --port 8080
```

## Interfaces

**CLI** — `pcg` for local indexing, repository management, search, and graph-backed analysis.

**MCP** — Connect PCG to AI development tools so questions resolve against real code and infrastructure context.

**HTTP API** — OpenAPI-backed API for service-to-service automation, internal tools, and agent frameworks.

**Deployable Service** — Run PCG as a networked service with a stateless API runtime, a stateful repository ingester, external Neo4j, and external Postgres.

## Deploy

Minimal Kubernetes manifests:

```bash
kubectl apply -k deploy/manifests/minimal
```

Helm:

```bash
helm install platform-context-graph ./deploy/helm/platform-context-graph
```

Public distribution targets:

- Docker image: `ghcr.io/platformcontext/platform-context-graph`
- OCI Helm chart: `oci://ghcr.io/platformcontext/charts/platform-context-graph`

The chart is designed for the production shape used in EKS:

- external Neo4j
- external Postgres for indexed content retrieval and search
- API `Deployment` for HTTP + MCP
- repository ingester `StatefulSet` with attached workspace storage
- repo rediscovery filtered by exact/regex repository rules over normalized `org/repo` identifiers
- flexible exposure through `ClusterIP`, `Ingress`, `HTTPRoute`, or `LoadBalancer`

For local end-to-end testing:

```bash
docker compose up --build
```

## Documentation

- Developer guide: [DEVELOPING.md](DEVELOPING.md) — parser architecture, adding languages, integration testing, spec contracts
- Docs site source: [docs/](docs/)
- Quickstart: [docs/docs/getting-started/quickstart.md](docs/docs/getting-started/quickstart.md)
- MCP Guide: [docs/docs/guides/mcp-guide.md](docs/docs/guides/mcp-guide.md)
- HTTP API: [docs/docs/reference/http-api.md](docs/docs/reference/http-api.md)
- Deployment Overview: [docs/docs/deployment/overview.md](docs/docs/deployment/overview.md)

## Acknowledgment

PlatformContextGraph builds on the original [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext) project by [Shashank Shekhar Singh](https://github.com/Shashankss1205) and its contributors. Their work established the foundation this repository started from.

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for the attribution note.
