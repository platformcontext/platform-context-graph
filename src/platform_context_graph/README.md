# PlatformContextGraph Source Package

This directory contains the importable Python package for PlatformContextGraph.

Top-level packages are organized by responsibility:

- `app`: service-role entrypoints and startup wiring.
- `collectors`: source-specific collection logic such as the Git collector.
- `api`: HTTP application and routers.
- `cli`: Typer entrypoint, commands, helpers, and setup flows.
- `facts`: future boundary for fact-first storage and normalization contracts.
- `graph`: canonical graph schema and persistence helpers.
- `core`: storage, jobs, and database plumbing.
- `domain`: shared typed response and entity models.
- `mcp`: MCP server, transport, tool registry, and tool handlers.
- `observability`: OpenTelemetry bootstrap and metrics helpers.
- `parsers`: parser registry, parser capabilities, language parsers, and SCIP helpers.
- `platform`: future home for shared platform/runtime infrastructure primitives.
- `query`: read-side graph context queries.
- `resolution`: workload and platform materialization and future shared resolution logic.
- `relationships`: evidence-backed repository relationship discovery and resolution.
- `runtime`: sync and background runtime orchestration.
- `tools`: GraphBuilder facade, compatibility shims, and remaining legacy helpers.
- `utils`: reusable cross-cutting helpers.
- `viz`: graph visualization utilities.
