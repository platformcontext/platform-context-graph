# PlatformContextGraph

**A self-hosted Code-to-cloud context graph for engineering teams and AI systems.**

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
  <img src="https://img.shields.io/badge/go-1.25%2B-00ADD8?style=flat-square&logo=go" alt="Go 1.25+">
  <img src="https://img.shields.io/badge/ghcr.io-image-2496ED?style=flat-square&logo=docker&logoColor=white" alt="GHCR Image">
  <img src="https://img.shields.io/badge/helm-OCI-0F1689?style=flat-square&logo=helm&logoColor=white" alt="Helm OCI Chart">
</p>

PlatformContextGraph (PCG) builds one queryable model across source code,
Terraform, Helm, Kubernetes, Argo CD, Crossplane, and runtime topology. It is
designed for teams that need to answer questions that span repositories,
services, workloads, and infrastructure without stitching the answer together by
hand.

## Why Teams Use PCG

PCG is useful when the answer is spread across code, infrastructure, and runtime
context instead of sitting in one repository.

What that looks like in practice:

- **Software engineers**
  - "Who calls `process_payment` across all indexed repos?"
  - "What breaks if I change this shared client or interface?"
- **DevOps and platform engineers**
  - "What deploys this service, and which repos feed that deployment path?"
  - "What infrastructure does this workload depend on?"
- **SRE and on-call**
  - "What other workloads share this database or queue?"
  - "Is the backlog growing because of parsing, Postgres, or graph projection?"
- **AI-assisted development**
  - "Trace this cloud resource back to the code that defines it."
  - "Explain how these two services are connected."

Core strengths:

- one graph for code and infrastructure
- the same query model over CLI, MCP, and HTTP API
- deployable shared service with API, MCP server, ingester, and resolution-engine runtimes
- facts-first indexing for durability, recovery, and operator visibility
- direct code-to-cloud tracing, blast radius, and environment comparison

Starter examples are collected in [Starter Prompts](docs/docs/guides/starter-prompts.md). The highest-value prompts explicitly ask PCG to scan all related repositories, deployment sources, and indexed documentation before answering.

PCG exposes the same graph through:

- a local CLI for indexing and analysis
- MCP for AI development tools
- an HTTP API for automation and internal platforms
- a deployable service shape for continuous indexing and shared use

## Quick Start

Choose the path that matches what you want to do first.

PCG is not a self-contained CLI — it always reads and writes through Neo4j
and Postgres, and `pcg index`, `pcg list`, and `pcg analyze …` all require a
running API + data plane. Pick the path that stands those up for you.

### Run the full platform locally

Bring up Neo4j, Postgres, the API, the ingester, the resolution engine, and
the one-shot bootstrap indexer with one command:

```bash
docker compose up --build
```

This starts:

- Neo4j
- Postgres
- OpenTelemetry collector
- Jaeger
- a one-shot bootstrap indexer
- the API runtime
- the MCP server runtime
- the ingester runtime
- the resolution-engine runtime

### Use the CLI against the running stack

Build and put `pcg` on `PATH`:

```bash
cd go && go build -o bin/ ./cmd/pcg ./cmd/bootstrap-index
export PATH="$PWD/bin:$PATH"
pcg --help
```

The CLI talks to the API at `http://localhost:8080` by default. Point it at
the Compose-started Neo4j and Postgres when indexing locally:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph

pcg index .                              # runs pcg-bootstrap-index against your DBs
pcg list                                 # reads the API
pcg analyze callers process_payment      # reads the API
```

`pcg index` invokes the `pcg-bootstrap-index` binary, so build that binary
too (shown above). `pcg list` and `pcg analyze …` are HTTP clients — they
require the `platform-context-graph` API service (started by Compose) to be
reachable.

### Deploy to Kubernetes

Use Helm for the supported split-service deployment shape:

```bash
helm install platform-context-graph ./deploy/helm/platform-context-graph
```

For the operator view of the deployed services, start with
[Service Runtimes](docs/docs/deployment/service-runtimes.md) and
[Deployment Overview](docs/docs/deployment/overview.md).

## How It Works

PCG now uses a facts-first indexing flow for deployed Git ingestion.

```mermaid
flowchart LR
  A["Git collector"] --> B["Parse repository snapshot"]
  B --> C["Postgres fact store"]
  C --> D["Fact work queue"]
  D --> E["Resolution Engine"]
  E --> F["Canonical graph projection"]
  F --> G["Neo4j"]
  F --> H["Postgres content store"]
  I["CLI / MCP / HTTP API"] --> G
  I --> H
```

In practice, that means:

1. the ingester discovers repositories and parses a snapshot
2. repository, file, and entity facts are written to Postgres
3. the resolution-engine claims the queued work
4. canonical graph, relationships, workloads, and platform edges are projected
5. API, MCP, and CLI analysis surfaces read the resulting graph and content

## Runtime Model

The deployed platform has five long-running runtimes plus two one-shot helpers:

| Runtime | What it owns | Default command |
| --- | --- | --- |
| DB Migrate | Postgres + Neo4j schema DDL before the long-running workloads start | `/usr/local/bin/pcg-bootstrap-data-plane` |
| API | HTTP API, graph and content reads, admin endpoints | `pcg api start --host 0.0.0.0 --port 8080` |
| MCP Server | MCP transport plus mounted query routes | `pcg mcp start` |
| Ingester | repo sync, workspace ownership, parsing, fact emission | `/usr/local/bin/pcg-ingester` |
| Workflow Coordinator | trigger intake, claims, completeness, and dark-mode control-plane validation | `/usr/local/bin/pcg-workflow-coordinator` |
| Resolution Engine | queue draining, fact loading, projection, retries, recovery | `/usr/local/bin/pcg-reducer` |
| Bootstrap Index | initial one-shot indexing before steady-state sync | `/usr/local/bin/pcg-bootstrap-index` |

The Workflow Coordinator is gated behind the `workflow-coordinator` Docker
Compose profile and is off in the default local stack.

See [Service Runtimes](docs/docs/deployment/service-runtimes.md) for the
complete runtime contract.

## Observability

PCG ships with first-class observability for operators and performance work:

- OTLP metrics and traces
- JSON logs
- direct Prometheus-format `/metrics` endpoints per runtime
- optional Kubernetes `ServiceMonitor` resources for API, MCP, ingester,
  workflow-coordinator, and resolution-engine

In local Compose runs, you can inspect the runtime scrape endpoints directly:

- API: `http://localhost:19464/metrics`
- Ingester: `http://localhost:19465/metrics`
- Resolution Engine: `http://localhost:19466/metrics`
- Bootstrap Index: `http://localhost:19467/metrics`
- MCP Server: `http://localhost:19468/metrics`
- Workflow Coordinator: `http://localhost:19469/metrics` (enabled via compose profile)

See:

- [Telemetry Overview](docs/docs/reference/telemetry/index.md)
- [Telemetry Metrics](docs/docs/reference/telemetry/metrics.md)
- [Docker Compose](docs/docs/deployment/docker-compose.md)
- [Helm Deployment](docs/docs/deployment/helm.md)

## What You Can Ask

Examples:

- "Who calls `process_payment` across all indexed repos?"
- "What infrastructure does this service depend on?"
- "Trace this resource back to the code that defines it."
- "What breaks if I change this Terraform module?"
- "How does prod differ from staging for this workload?"

Role-based prompt sets and follow-up patterns live in
[Starter Prompts](docs/docs/guides/starter-prompts.md).

## Quick Navigation

- CLI: local indexing, search, and graph-backed analysis
- MCP: AI tooling and assistant integrations
- HTTP API: automation and internal platforms
- Deploy: Docker Compose, Helm, and GitOps deployment paths

## Documentation Paths

Start with the path that matches what you are doing:

- Getting started:
  [Quickstart](docs/docs/getting-started/quickstart.md)
- AI tooling:
  [MCP Guide](docs/docs/guides/mcp-guide.md)
- Prompt cookbook:
  [Starter Prompts](docs/docs/guides/starter-prompts.md)
- Deployment:
  [Deployment Overview](docs/docs/deployment/overview.md)
- Operations:
  [Service Runtimes](docs/docs/deployment/service-runtimes.md)
- Architecture:
  [System Architecture](docs/docs/architecture.md)
- Verification:
  [Local Testing Runbook](docs/docs/reference/local-testing.md)
- Local Compose:
  [Docker Compose](docs/docs/deployment/docker-compose.md)

## Verification

Canonical Go test gates — run these before opening a pull request. The full
matrix lives in [Local Testing Runbook](docs/docs/reference/local-testing.md).

```bash
cd go && go test ./cmd/pcg ./cmd/api ./cmd/mcp-server ./internal/query ./internal/mcp -count=1
cd go && go test ./internal/parser ./internal/collector/discovery ./internal/content/shape ./internal/collector -count=1
cd go && go test ./internal/terraformschema ./internal/relationships -count=1
cd go && go test ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer ./internal/runtime ./internal/status ./internal/storage/postgres -count=1
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Project Notes

PCG is self-hosted and does not require outbound vendor telemetry. When
observability is enabled, it uses your configured OTLP and Prometheus targets.
