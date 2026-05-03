# Installation

Install PCG by choosing the local path you need.

Use [Local binaries](../run-locally/local-binaries.md) when you are developing
PCG or want one workspace owner. That page has the current Go build commands,
the NornicDB install command, and the `pcg graph start` workflow.

Use [Docker Compose](../run-locally/docker-compose.md) when you want the full
local service stack. Compose starts Postgres, the graph backend, API, MCP
server, ingester, reducer, bootstrap indexer, OTEL collector, and Jaeger.

NornicDB is the default graph backend. Neo4j remains the explicit supported
compatibility path.

After installing the binaries, `pcg doctor` checks the local CLI and helper
binary wiring. Graph checks depend on whether the selected backend is running.
