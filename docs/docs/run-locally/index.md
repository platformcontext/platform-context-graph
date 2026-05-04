# Run locally

Use the local docs when you want PCG running on your laptop. There are two
paths, and they solve different problems.

| Path | Use it when | What starts |
| --- | --- | --- |
| [Local binaries](local-binaries.md) | You are developing PCG or want one workspace owner | embedded Postgres, embedded NornicDB, ingester, reducer |
| [Docker Compose](docker-compose.md) | You want the full laptop service stack | Postgres, graph backend, API, MCP server, ingester, reducer, bootstrap indexer |

If you are not sure, start with Docker Compose. It gives you the same service
shape you will later deploy for a team.

Use local binaries when you need to test the `pcg graph start` workflow, debug
runtime behavior, or work on PCG itself.

## Storage

The default graph backend is NornicDB. Neo4j is the explicit official
alternative. Postgres stores relational state, facts, queues, status, content,
and recovery data.

## Local commands and API commands

`pcg index` invokes the `pcg-bootstrap-index` binary and writes to the
configured graph and Postgres stores.

`pcg list`, `pcg stats`, and `pcg analyze ...` call the API. In Docker Compose,
that API is available at `http://localhost:8080`.

## Next steps

- [Run local binaries](local-binaries.md)
- [Run Docker Compose](docker-compose.md)
- [Connect MCP locally](mcp-local.md)
- [Index repositories](../use/index-repositories.md)
