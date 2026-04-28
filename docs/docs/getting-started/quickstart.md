# Quickstart

This quickstart gets you from zero to useful answers in the shortest path
possible.

!!! note "PCG always needs Neo4j + Postgres"
    `pcg` is not a self-contained CLI. `pcg index` invokes the
    `pcg-bootstrap-index` binary and writes directly into Neo4j and
    Postgres. `pcg list`, `pcg stats`, and `pcg analyze …` are HTTP clients
    that call the API server. Stand the stack up before running any of the
    commands below.

## 1. Start the stack

The fastest path is Docker Compose from the repository root:

```bash
docker compose up --build
```

This brings up Neo4j, Postgres, the API, the MCP server, the ingester, the
resolution engine, and a one-shot bootstrap indexer.

Point the CLI at the Compose-managed services:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
```

The CLI defaults to the API at `http://localhost:8080`; no extra env var is
needed for the read-side commands unless you target a different host.

## 2. Index a repository

Start with a repository or mono-folder you actually care about:

```bash
pcg index .
```

PCG already skips hidden and well-known cache trees such as `.git`,
`.terraform`, `.terragrunt-cache`, `.pulumi`, `.crossplane`, `.serverless`,
`.aws-sam`, and `cdk.out`. It also excludes built-in dependency roots such as
`vendor/`, `node_modules/`, `site-packages/`, and `deps/` before parse by
default. If you also need to exclude generated files, local state, or other
repo-specific paths, add a `.pcgignore` file and see the
[.pcgignore guide](../reference/pcgignore.md).

## 3. Confirm what is indexed

```bash
pcg list
```

You should see the repository appear in the graph.

## 4. Ask a code-only question

```bash
pcg analyze callers process_payment
```

This is the fastest way to prove the graph is already useful even before you
bring infrastructure context into the picture.

## 5. Connect MCP for AI-assisted workflows

If you want your IDE or agent to talk to PCG over MCP, configure the client
once:

```bash
pcg mcp setup
```

The Docker Compose stack already runs the MCP server (`mcp-server` service).
Use `pcg mcp start` only when you want a stdio MCP process that shells out
to the same API service — it is not a replacement for the running API + data
plane.

## What to do next

- Explore [MCP Guide](../guides/mcp-guide.md) for IDE and agent workflows.
- Explore [HTTP API](../reference/http-api.md) for structured automation.
- Explore [Deployment Overview](../deployment/overview.md) if you want the full service in Docker or Kubernetes.
- Explore [CLI Indexing](../reference/cli-indexing.md) and [CLI Analysis](../reference/cli-analysis.md) for more code-first workflows.
