# MCP Guide

The Model Context Protocol is how PCG plugs into AI development tools. MCP is the fastest way to give an assistant direct access to graph-backed code and infrastructure context without inventing a separate prompt wrapper for every task.

## Setup

Run the setup wizard:

```bash
pcg mcp setup
```

The wizard can write or update the configuration for supported clients and gives you a usable config snippet even when you need to wire a client manually.

## Start the server

For stdio-based MCP:

```bash
pcg mcp start
```

For a combined HTTP + MCP networked service:

```bash
pcg serve start --host 0.0.0.0 --port 8080
```

## What MCP is good at

- asking code-only questions such as callers, callees, dead code, or complexity
- resolving repositories, workloads, and infrastructure entities into canonical graph context
- retrieving source content by `repo_id + relative_path` or `entity_id`
- searching indexed source text through the PostgreSQL content store
- tracing shared resources back to workloads and code
- giving an AI assistant real dependency and deployment context during refactors or debugging

## Repository access handoff

When PCG is deployed remotely, repository or content results may include `repo_access` metadata.

- For `get_file_content`, `get_file_lines`, and `get_entity_content`, PCG first tries the PostgreSQL content store and then falls back to the server workspace or graph cache.
- Read responses include `source_backend`, which tells the client whether the answer came from `postgres`, `workspace`, `graph-cache`, or `unavailable`.
- `search_file_content` and `search_entity_content` require the PostgreSQL content store. They do not fall back to workspace scanning.
- If the server can satisfy a read request from Postgres or its shared checkout volume, it should return the content directly and not ask the user to clone anything locally.
- `repo_access` is for workflows that genuinely need the user's machine, such as opening or editing a local checkout that the server cannot reach.

- On stdio MCP clients that advertise `elicitation`, PCG can issue a real `elicitation/create` request to ask for a local checkout path or a local clone decision.
- On clients without `elicitation`, or on the current HTTP JSON-RPC transport, PCG falls back to conversational handoff.
- `local_path` is the server-side checkout path, not a guaranteed path on the user's machine.

## Recommended question patterns

- "Who calls `process_payment`?"
- "What workload uses this queue in prod?"
- "Trace this RDS cluster back to the Terraform module and repos."
- "What changes if I modify this service?"
- "Compare stage and prod for this workload."

## Related docs

- [MCP Reference](../reference/mcp-reference.md)
- [MCP Cookbook](../reference/mcp-cookbook.md)
- [HTTP API](../reference/http-api.md)
- [Shared Infra Trace](shared-infra-trace.md)
