# Docker Compose

Use Docker Compose when you want the full PCG service stack on your laptop.
This is the easiest local path for trying API, MCP, ingestion, reduction,
telemetry, Postgres, and the graph backend together.

## Start the default stack

From the repository root:

```bash
docker compose up --build
```

The default stack uses NornicDB for graph storage and Postgres for relational
state, facts, queues, status, content, and recovery data.

It starts:

- NornicDB
- Postgres
- API
- MCP server
- ingester
- reducer
- bootstrap indexer
- OpenTelemetry collector
- Jaeger

## Start the Neo4j stack

Neo4j is the explicit supported compatibility graph backend:

```bash
docker compose -f docker-compose.neo4j.yml up --build
```

Use this when you need to validate Neo4j behavior or migrate an existing Neo4j
deployment path.

## Point local CLI commands at Compose

The API is available at `http://localhost:8080` by default. For indexing into
the default NornicDB Compose stack, use:

```bash
export PCG_GRAPH_BACKEND=nornicdb
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=nornic
export PCG_NEO4J_DATABASE=nornic
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
```

Then index and query:

```bash
pcg index .
pcg list
pcg analyze callers process_payment
```

If you use `docker-compose.neo4j.yml`, set `PCG_GRAPH_BACKEND=neo4j` and use
database `neo4j` instead of `nornic`.

## Local endpoints

- API: `http://localhost:8080`
- MCP server: `http://localhost:8081`
- Jaeger: `http://localhost:16686`
- Postgres: `localhost:15432`
- Graph Bolt endpoint: `localhost:7687`

See [Connect MCP locally](mcp-local.md) for MCP client setup.
