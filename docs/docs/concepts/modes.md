# CLI Mode vs. MCP Mode

PCG exposes the same graph through multiple interfaces. The right entry point depends on who is driving the workflow.

## CLI

Use the CLI when you are driving the work directly from a terminal.

- **Best for:** local indexing, ad hoc analysis, debugging, repository management
- **Interface:** terminal

Example:

```bash
pcg analyze callers process_payment
```

## MCP

Use MCP when your editor or agent is the primary caller.

- **Best for:** AI-assisted development, debugging, natural-language graph queries
- **Interface:** IDE or chat client over MCP
- **Interactive handoff:** stdio MCP can use protocol-side elicitation when the client advertises support

Example workflow:

1. ask your AI tool "What workloads use this queue?"
2. the client calls PCG over MCP
3. PCG resolves the question against the graph and returns structured context

## HTTP API

Use the HTTP API when you need a stable contract for automation, tooling, or a deployed service.

- **Best for:** service-to-service automation, shared PCG deployments, agent frameworks
- **Interface:** OpenAPI-backed HTTP endpoints
- **Handoff behavior:** repository access stays conversational because the current HTTP JSON-RPC endpoint is not duplex

All three surfaces share the same query model, so the graph answers should stay consistent across CLI, MCP, and HTTP.
