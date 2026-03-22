# PlatformContextGraph

**Code-to-cloud context graph for AI-assisted engineering.**

PlatformContextGraph gives AI systems and engineers a fast, queryable map of code, dependencies, infrastructure, workloads, and deployment topology. Use it to answer code-only questions, trace cloud resources back to source, and power development, debugging, troubleshooting, and re-architecture workflows with real graph-backed context.

[Get Started](getting-started/quickstart.md){ .md-button .md-button--primary }
[Deploy](deployment/overview.md){ .md-button }
[HTTP API](reference/http-api.md){ .md-button }
[MCP Guide](guides/mcp-guide.md){ .md-button }

## Why PCG

- **One graph for code and infrastructure.** Index source code, Terraform, Helm, Kubernetes, Argo CD, and related deployment assets in the same model.
- **Built for AI workflows.** Expose the same query model over the CLI, MCP, and a first-class HTTP API.
- **Service and workload aware.** Reason about workloads, workload instances, shared infrastructure, and environment drift.
- **Portable source retrieval.** Resolve files by `repo_id + relative_path` and entities by `entity_id`, with Postgres-backed content search and deployed-service content retrieval.
- **Deployable as a real service.** Run it locally with Docker Compose or deploy it to Kubernetes with Helm and Argo CD.

## Primary Interfaces

### CLI

Use `pcg` locally for indexing, repository management, search, and graph-backed analysis.

### MCP

Connect PCG to AI development tools so natural-language questions resolve against real code and infrastructure context.

### HTTP API

Use the OpenAPI-backed API for service-to-service automation, internal tools, and agent frameworks that need a stable contract.

### Deployable Service

Run PCG as a networked service with a stateless API runtime, a stateful repository ingester, and HTTP + MCP access over one product surface.

## Common Workflows

- **Code relationships only:** search for symbols, callers, callees, and complex or dead code without needing any infrastructure mapping.
- **Code to cloud tracing:** start from a workload, resource, queue, bucket, image, or Terraform module and walk back to repos and code.
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
- [Fixture Ecosystems](guides/fixture-ecosystems.md)
- [Graph Model](concepts/graph-model.md)
- [Architecture](architecture.md)
