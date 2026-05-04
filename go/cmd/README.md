# Commands

Each subdirectory builds one PCG executable. This directory is a navigation
root, not a Go package — each child has its own rich `README.md` and
`AGENTS.md`.

The public CLI command is `pcg`. The service binaries use PCG-prefixed names
when installed for local runtime work, such as `pcg-api`, `pcg-mcp-server`,
`pcg-ingester`, and `pcg-reducer`. Use `scripts/install-local-binaries.sh`
from the repository root when you need that exact binary set on `PATH`.

## Binary-to-runtime map

| Binary | Subdirectory | Lifecycle |
| --- | --- | --- |
| `pcg` (CLI) | `pcg/` | One-shot CLI commands plus subcommand dispatch |
| `pcg-api` | `api/` | Long-running HTTP API |
| `pcg-mcp-server` | `mcp-server/` | Long-running MCP tool server |
| `pcg-ingester` | `ingester/` | Long-running git sync + parse + fact emission |
| `pcg-projector` | `projector/` | Long-running source-local projection (local profiles) |
| `pcg-reducer` | `reducer/` | Long-running cross-domain materialization |
| `pcg-bootstrap-index` | `bootstrap-index/` | One-shot multi-phase orchestration |
| `pcg-bootstrap-data-plane` | `bootstrap-data-plane/` | One-shot data-plane setup |
| `pcg-collector-git` | `collector-git/` | Local git-collector helper |
| `pcg-admin-status` | `admin-status/` | Admin/status read helper |
| `pcg-workflow-coordinator` | `workflow-coordinator/` | Long-running workflow coordinator |

## Pipeline shape

```mermaid
flowchart LR
  ingester[ingester] --> postgres[(postgres facts/queue)]
  projector[projector] -.local profiles.-> postgres
  postgres --> reducer[reducer]
  reducer --> graph[(graph backend)]
  bootstrap[bootstrap-index] -.one-shot.-> ingester
  bootstrap -.one-shot.-> reducer
  api[api] --> graph
  api --> postgres
  mcp[mcp-server] --> api
  workflow[workflow-coordinator] --> postgres
```

For the full lifecycle of any one binary, open its `README.md` and
`AGENTS.md`.

## Per-package documentation convention

Every Go package directory under `go/cmd/` carries three files:

- `doc.go` — godoc contract.
- `README.md` — architectural and operational lens with mermaid flow
  diagrams and runbook-shape operational notes.
- `AGENTS.md` — guidance for LLM assistants editing the binary.

## Dependencies

Each `cmd/` subdirectory wires together internal packages into a binary;
see the per-binary `main.go` for the exact set. Shared process wiring
lives in `internal/runtime` and `internal/app`.

## Telemetry

Process-level telemetry bootstrap (service namespace, OTEL exporter, log
sinks) is configured by `internal/runtime` and `internal/telemetry`. Each
binary inherits that contract; packages do not register their own meter
providers.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/cli-reference.md`
- `docs/docs/reference/local-testing.md`
