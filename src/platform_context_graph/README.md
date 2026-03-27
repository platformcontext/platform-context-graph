# PlatformContextGraph Source Package

This directory contains the importable Python package for PlatformContextGraph.

Top-level packages are organized by responsibility:

- `api`: HTTP application and routers.
- `cli`: Typer entrypoint, commands, helpers, and setup flows.
- `core`: storage, jobs, and database plumbing.
- `domain`: shared typed response and entity models.
- `mcp`: MCP server, transport, tool registry, and tool handlers.
- `observability`: OpenTelemetry bootstrap and metrics helpers.
- `query`: read-side graph context queries.
- `relationships`: evidence-backed repository relationship discovery and resolution.
- `runtime`: sync and background runtime orchestration.
- `tools`: indexer, parsers, and graph-building helpers.
- `utils`: reusable cross-cutting helpers.
- `viz`: graph visualization utilities.
