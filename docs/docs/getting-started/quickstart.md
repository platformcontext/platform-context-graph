# Quickstart

The local setup docs now split the two laptop paths.

If you want one workspace owner from your terminal, use
[Local binaries](../run-locally/local-binaries.md). That path builds the Go
binaries, installs NornicDB, and starts `pcg graph start`.

If you want the full local service stack, use
[Docker Compose](../run-locally/docker-compose.md). That path starts the API,
MCP server, ingester, reducer, bootstrap indexer, Postgres, graph backend,
OTEL collector, and Jaeger.

For MCP client setup, use [Local MCP](../run-locally/mcp-local.md).

`pcg index` invokes `pcg-bootstrap-index`. `pcg list`, `pcg stats`, and
`pcg analyze` need an API process.
