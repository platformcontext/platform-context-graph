# Index repositories

Indexing is how PCG turns source code and infrastructure files into facts,
content, and graph relationships.

## Index from Docker Compose

Start the full local stack first:

```bash
docker compose up --build
```

The default Compose API listens at `http://localhost:8080`. The MCP service
listens at `http://localhost:8081`.

Then point indexing at the Compose stores:

```bash
export PCG_GRAPH_BACKEND=nornicdb
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=nornic
export PCG_NEO4J_DATABASE=nornic
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph

pcg index .
```

`pcg index` invokes `pcg-bootstrap-index`, so build that binary when you are
running from source. It writes to the graph and Postgres stores configured in
the environment.

## Check what PCG sees

```bash
pcg list
pcg stats
```

These commands call the API. In the Compose stack, the API listens at
`http://localhost:8080`.

## Exclude local noise

PCG skips common cache and dependency directories by default, including `.git`,
`.terraform`, `.terragrunt-cache`, `.pulumi`, `node_modules`, `vendor`, and
`site-packages`.

Use `.pcgignore` for repo-specific generated files, local state, or large
fixtures that should not be indexed. See [.pcgignore](../reference/pcgignore.md).
