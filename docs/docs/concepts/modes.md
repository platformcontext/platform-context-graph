# Interfaces: CLI, MCP, and HTTP API

PCG exposes the same graph through three interfaces. Same query model, same capabilities — pick the one that fits your workflow.

## CLI

Use when you are driving the work directly from a terminal.

```bash
# Index a repo
pcg index /path/to/repo

# Find callers of a function
pcg analyze callers process_payment

# Find dead code while excluding route handlers
pcg analyze dead-code --repo-id repository:r_ab12cd34 --exclude @app.route --fail-on-found
```

**Best for:** local indexing, ad hoc analysis, scripting, debugging. The CLI is the fastest way to get answers when you already know what to ask.

## MCP

Use when your AI assistant is driving the workflow.

```bash
# Start the MCP server
pcg mcp start
```

Then ask your AI tool natural-language questions. The assistant calls PCG tools over MCP and gets structured graph context back:

- "What breaks if I change the payment service?" → calls `find_blast_radius`
- "How is this deployed?" → calls `trace_deployment_chain`
- "Compare prod and staging" → calls `compare_environments`

**Best for:** AI-assisted development, debugging with context, natural-language graph queries. MCP is how most engineers will interact with PCG day-to-day.

On stdio MCP clients that support elicitation (like Claude), PCG can prompt for local checkout paths directly through the protocol.

## HTTP API

Use when you need a stable contract for automation or a shared deployment.

```bash
# Start the HTTP server
pcg serve start --host 0.0.0.0 --port 8080
```

The HTTP API serves the same query capabilities as OpenAPI-backed endpoints, plus bundle import/export and repository management.

**Best for:** CI/CD pipelines, service-to-service automation, shared PCG deployments, custom agent frameworks.

## Which interface should I use?

| Workflow | Interface | Why |
|----------|-----------|-----|
| Local development | CLI | Direct, fast, scriptable |
| AI-assisted coding | MCP | Gives your assistant real graph context |
| CI/CD checks | CLI or HTTP | `pcg analyze` in pipelines, or query a shared server |
| Shared team deployment | HTTP | One server, many clients |
| Custom tooling | HTTP | OpenAPI contract for integration |

## Runtime roles

When deployed as a service, PCG runs in one of three roles:

- **combined** (default) — serves HTTP API and processes indexing
- **api** — serves HTTP API only, reads from the graph
- **ingester** — the deployed indexing runtime. Internally this still uses the `ingester` runtime role and processes indexing jobs only, writing facts and projected graph state.

Split roles when you need to scale API serving and indexing independently. See [Deployment Overview](../deployment/overview.md) for details.

## Next steps

- [MCP Guide](../guides/mcp-guide.md) — connect PCG to your AI assistant
- [HTTP API Reference](../reference/http-api.md) — full endpoint documentation
- [CLI Reference](../reference/cli-reference.md) — all CLI commands and flags
