# Quickstart

This quickstart gets you from zero to useful answers in the shortest path possible.

## 1. Index a repository

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

## 2. Confirm what is indexed

```bash
pcg list
```

You should see the repository appear in the graph.

## 3. Ask a code-only question

```bash
pcg analyze callers process_payment
```

This is the fastest way to prove the graph is already useful even before you bring infrastructure context into the picture.

## 4. Start MCP for AI-assisted workflows

Configure your client once:

```bash
pcg mcp setup
```

Then start the MCP server:

```bash
pcg mcp start
```

## 5. Start the combined service

If you want HTTP API access and a long-running MCP endpoint in one process:

```bash
pcg serve start --host 0.0.0.0 --port 8080
```

Then open:

- `GET /api/v0/openapi.json`
- `GET /api/v0/docs`
- `GET /api/v0/redoc`

## What to do next

- Explore [MCP Guide](../guides/mcp-guide.md) for IDE and agent workflows.
- Explore [HTTP API](../reference/http-api.md) for structured automation.
- Explore [Deployment Overview](../deployment/overview.md) if you want the full service in Docker or Kubernetes.
- Explore [CLI Indexing](../reference/cli-indexing.md) and [CLI Analysis](../reference/cli-analysis.md) for more code-first workflows.
