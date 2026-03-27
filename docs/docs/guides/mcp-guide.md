# MCP Guide

Your AI assistant sees one file at a time. It can read imports, guess at dependencies, and search for string matches — but it cannot see the Terraform module that provisions the database, the ArgoCD app that deploys the workload, or the three other repos that break if you change an API contract. MCP gives it the full dependency graph.

## Setup

Run the setup wizard to configure your MCP client:

```bash
pcg mcp setup
```

The wizard writes or updates configuration for supported clients (Claude, Cursor, VS Code) and gives you a config snippet for manual wiring.

## Start the server

For stdio-based MCP (local, single-user):

```bash
pcg mcp start
```

For a shared deployment over HTTP:

```bash
pcg serve start --host 0.0.0.0 --port 8080
```

## Before and after

**Without MCP** — you ask your AI assistant "What does the payment service depend on?"

The assistant greps imports in the current file, maybe finds a few Python packages. It has no visibility into Terraform modules, K8s manifests, ArgoCD apps, or cross-repo callers. It guesses.

**With MCP** — same question.

The assistant calls `get_service_context payment-service` and gets back: 4 downstream repos, 2 Terraform modules, an ArgoCD Application, 3 K8s resources, and a Crossplane claim. It answers with evidence from the graph, not hallucinated assumptions from a partial code snapshot.

## What MCP tools answer

| Question pattern | MCP tool |
|-----------------|----------|
| "Who calls this function?" | `analyze_code_relationships` |
| "What breaks if I change this service?" | `find_blast_radius` |
| "How is this deployed?" | `trace_deployment_chain` |
| "What provisions this database?" | `trace_resource_to_code` |
| "Compare prod and staging" | `compare_environments` |
| "What does this repo contain?" | `get_repo_context` |
| "Show me the source of this file" | `get_file_content` |
| "Search across indexed code" | `search_file_content` |
| "Find complex functions" | `find_most_complex_functions` |
| "What's dead code?" | `find_dead_code` |

## Story-first responses

For repository and deployment questions, PCG now returns a top-level `story` field on:

- `get_repo_summary`
- `trace_deployment_chain`

Use it this way:

1. start with `story`
2. use `deployment_overview` for grouped supporting context
3. use the detailed fields only when you need file-by-file evidence

This keeps answers concise without hiding the underlying evidence.

## Repository access handoff

When PCG is deployed remotely, the server may not have local access to every repository. Content retrieval follows a fallback chain:

1. **PostgreSQL content store** — preferred, fastest
2. **Server workspace** — shared checkout volume
3. **Graph cache** — metadata stored during indexing
4. **Conversational handoff** — asks the user for a local path

Read responses include `source_backend` so you know where the answer came from. On stdio MCP clients that support elicitation, PCG can prompt for a local checkout path directly through the protocol. On HTTP clients, it falls back to conversational handoff.

`search_file_content` and `search_entity_content` require the PostgreSQL content store — they do not fall back to workspace scanning.

## Troubleshooting

**"Tool not found"** — verify the MCP server is running (`pcg mcp start`) and your client config points to the correct command or URL.

**"No repositories indexed"** — MCP queries the graph, which requires indexing first. Run `pcg index /path/to/repo` or start docker-compose to index fixtures.

**Slow responses** — large graphs on FalkorDB Lite may hit memory limits. Switch to Neo4j for production-scale graphs.

## Related docs

- [MCP Reference](../reference/mcp-reference.md) — full tool list with parameters
- [MCP Cookbook](../reference/mcp-cookbook.md) — detailed query examples
- [HTTP API](../reference/http-api.md) — automation and service-to-service access
- [Shared Infra Trace](shared-infra-trace.md) — cross-repo infrastructure tracing
