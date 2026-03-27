# PlatformContextGraph

**Code-to-cloud context graph for AI-assisted engineering.**

PlatformContextGraph gives AI systems and engineers a queryable map of code, dependencies, infrastructure, workloads, and deployment topology. Use it to answer code-level questions, trace cloud resources back to source, and power development, debugging, and re-architecture workflows with graph-backed context.

[Get Started](getting-started/quickstart.md){ .md-button .md-button--primary }
[Deploy](deployment/overview.md){ .md-button }
[HTTP API](reference/http-api.md){ .md-button }
[MCP Guide](guides/mcp-guide.md){ .md-button }
[Relationship Graphs](guides/relationship-graphs.md){ .md-button }

## Why PCG

- **One graph for code and infrastructure.** Index source code, Terraform, Helm, Kubernetes, Argo CD, Crossplane, and CloudFormation in the same model.
- **Built for AI workflows.** The same query model is available over CLI, MCP, and HTTP API.
- **Service and workload aware.** Reason about workloads, shared infrastructure, and environment drift.
- **Portable source retrieval.** Resolve files by `repo_id + relative_path` and entities by `entity_id`, backed by Postgres content search.
- **Deployable as a service.** Run locally with Docker Compose or deploy to Kubernetes with Helm and Argo CD.

## Primary Interfaces

### CLI

`pcg` for local indexing, repository management, search, and graph-backed analysis.

### MCP

Connect PCG to AI development tools so questions resolve against real code and infrastructure context.

### HTTP API

OpenAPI-backed API for service-to-service automation, internal tools, and agent frameworks.

### Deployable Service

Run PCG as a networked service with a stateless API runtime, a stateful repository ingester, and HTTP + MCP access over one surface.

## Common Workflows

- **Code relationships:** search for symbols, callers, callees, and complex or dead code without needing infrastructure mapping.
- **Code-to-cloud tracing:** start from a workload, resource, queue, bucket, image, or Terraform module and walk back to repos and code.
- **Change impact analysis:** find the blast radius of a repository, workload, API, or shared infrastructure component.
- **Environment comparison:** compare stage and prod workload instances, backing resources, and configuration-linked dependencies.

## Start Where You Are

### Local development

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [CLI Reference](reference/cli-reference.md)

### AI-assisted workflows

- [MCP Guide](guides/mcp-guide.md)
- [MCP Reference](reference/mcp-reference.md)
- [MCP Cookbook](reference/mcp-cookbook.md)

### Deployable service

- [Deployment Overview](deployment/overview.md)
- [Docker Compose](deployment/docker-compose.md)
- [Helm](deployment/helm.md)
- [Argo CD](deployment/argocd.md)

### Deep dives

- [Shared Infra Trace](guides/shared-infra-trace.md)
- [Relationship Graph Examples](guides/relationship-graphs.md)
- [Fixture Ecosystems](guides/fixture-ecosystems.md)
- [Graph Model](concepts/graph-model.md)
- [Architecture](architecture.md)
