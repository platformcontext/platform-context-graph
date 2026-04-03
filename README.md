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

## Why Teams Use PCG

Your AI assistant can read your code. It cannot see the Terraform that provisions your database, the ArgoCD application that deploys your service, the three other repos whose workloads share that RDS instance, or the queue consumer that breaks when you change an API contract. Engineers fill that gap by hand — switching between repos, cloud consoles, IaC files, and the person who set it all up two years ago.

PlatformContextGraph builds one queryable graph across source code, Terraform, Helm, Kubernetes, ArgoCD, Crossplane, CloudFormation, and running workloads. Then it exposes that graph through CLI, MCP, and HTTP API so both engineers and AI assistants can trace dependencies, assess blast radius, and compare environments before they ship.

**What you can ask:**

_Code understanding & search:_

- _"Who calls `process_payment` across all indexed repos?"_ → `analyze_code_relationships`
- _"What implements this interface?"_ → `find_code`
- _"Show me the most complex functions in this repo"_ → `find_most_complex_functions`
- _"What code is dead — defined but never called?"_ → `find_dead_code`

_Change impact & safety:_

- _"What breaks if I change this service?"_ → `find_blast_radius`
- _"What's the blast radius of modifying this Terraform module?"_ → `find_change_surface`
- _"Explain how these two repos are connected"_ → `explain_dependency_path`

_Infrastructure & deployment tracing:_

- _"What infrastructure does this service depend on?"_ → `trace_deployment_chain`
- _"Trace this RDS instance back to the code that defines it"_ → `trace_resource_to_code`
- _"How does prod differ from staging for this workload?"_ → `compare_environments`
- _"What workloads share this database?"_ → `find_infra_resources` / `analyze_infra_relationships`

**Who uses it:**

- **Software engineers** — callers, callees, dead code, complexity hotspots, and blast radius before you merge.
- **Platform / DevOps / SRE** — deployment chains, shared infrastructure, environment comparison, incident tracing.
- **Security & compliance** — trace dependencies across repos, find what services access a shared resource, audit infrastructure relationships.
- **Architects & tech leads** — ecosystem overview, cross-repo dependency health, complexity hotspots, change surface analysis.
- **New engineers** — repo and service context, dependency explanations, deployment topology without tribal knowledge.

Open source. Apache 2.0 licensed. Self-hosted. No telemetry. [30+ language parsers](docs/docs/contributing-language-support.md), first-class IaC support, extensible by design.

[Why PCG →](docs/docs/why-pcg.md) · [Quickstart →](docs/docs/getting-started/quickstart.md) · [MCP Guide →](docs/docs/guides/mcp-guide.md) · [Relationship Graph Examples →](docs/docs/guides/relationship-graphs.md)

## What is this

PlatformContextGraph started as a fork of [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext), which builds a graph of source code relationships for AI-assisted development. That was a good starting point, but we needed more. PlatformContextGraph is a **Code-to-cloud context graph** for teams that need to connect source code, infrastructure, and running workloads in one place.

We needed the graph to understand infrastructure — Terraform modules, Helm charts, Kubernetes manifests, ArgoCD Applications, Crossplane XRDs, CloudFormation stacks. We needed to trace from a running workload back to the repo and code that defines it. We needed it to run on the network as a service, not just on a developer's laptop. And we needed it deployable to Kubernetes with proper separation of API and ingester workloads.

So we rebuilt it into that.

## What we built that's new

**IaC-native graph** — First-class parsers for Terraform/HCL, Kubernetes manifests, ArgoCD Applications and ApplicationSets, Crossplane XRDs, CloudFormation, Helm, and Kustomize. Infrastructure is a first-class citizen in the graph, not an afterthought.

**Bidirectional tracing** — Trace from a cloud resource back to the repo and code that defines it, or from code forward to what it deploys. `trace_resource_to_code`, `trace_deployment_chain`, `explain_dependency_path`.

**Blast radius and change surface** — Before you merge, see what breaks. Transitive dependency analysis across repos and infrastructure boundaries.

**Deployable service architecture** — Stateless API Deployment + stateful Ingester StatefulSet + standalone Resolution Engine Deployment. Neo4j for the graph, Postgres for portable content retrieval and fact storage. Helm chart, Kustomize manifests, and ArgoCD overlays included.

**Portable content model** — Queries return `repo_id + relative_path`, not server filesystem paths. The Postgres content store means the API serves source code without needing the repo checked out locally.

**Three interfaces, one query model** — CLI for local dev, MCP for AI assistants, HTTP API for automation. Same capabilities everywhere.

**Multi-repo ecosystem indexing** — Index entire orgs. Cross-repo dependency resolution. Environment comparison across prod, staging, and dev.

**Repo-scoped ingest boundaries** — Repo and workspace indexing honor each repository's own `.gitignore` by default, so generated and published assets stay out of routine ingest unless explicitly targeted.

**30+ language parsers** — Python, Go, TypeScript, Java, Rust, C/C++, and more via tree-sitter.

## Quick Navigation

- CLI: local indexing, search, and graph-backed analysis
- MCP: AI-assistant access to code and infrastructure context
- HTTP API: automation and service-to-service access
- Deploy: Docker Compose, Helm, Kustomize, and ArgoCD flows

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

**Deployable Service** — Run PCG as a networked service with a stateless API runtime, a stateful repository ingester, a standalone Resolution Engine, external Neo4j, and external Postgres.

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
- Architecture: [docs/docs/architecture.md](docs/docs/architecture.md)
- Source layout: [docs/docs/reference/source-layout.md](docs/docs/reference/source-layout.md)
- Quickstart: [docs/docs/getting-started/quickstart.md](docs/docs/getting-started/quickstart.md)
- MCP Guide: [docs/docs/guides/mcp-guide.md](docs/docs/guides/mcp-guide.md)
- Relationship Graph Examples: [docs/docs/guides/relationship-graphs.md](docs/docs/guides/relationship-graphs.md)
- HTTP API: [docs/docs/reference/http-api.md](docs/docs/reference/http-api.md)
- Deployment Overview: [docs/docs/deployment/overview.md](docs/docs/deployment/overview.md)

## Acknowledgment

PlatformContextGraph builds on the original [CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext) project by [Shashank Shekhar Singh](https://github.com/Shashankss1205) and its contributors. Their work established the foundation this repository started from.

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for the attribution note.
