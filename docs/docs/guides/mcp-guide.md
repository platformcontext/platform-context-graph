# MCP Guide

Your AI assistant sees one file at a time. It can read imports, guess at dependencies, and search for string matches — but it cannot see the Terraform module that provisions the database, the ArgoCD app that deploys the workload, or the three other repos that break if you change an API contract. MCP gives it the full dependency graph.

## Setup

If you want ready-to-use natural-language examples before wiring your client, start with [Starter Prompts](starter-prompts.md). For the strongest end-to-end answers, use the cross-repo prompt framing there: ask PCG to scan all related repositories, deployment sources, and indexed documentation before it explains a service or workload.

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

The assistant calls `get_service_story payment-service` and gets back a concise
story, the supporting evidence, and the drill-down handles to fetch raw context
only when needed. It answers with evidence from the graph, not hallucinated
assumptions from a partial code snapshot.

## What MCP tools answer

| Question pattern | MCP tool |
|-----------------|----------|
| "Who calls this function?" | `analyze_code_relationships` |
| "What breaks if I change this service?" | `find_blast_radius` |
| "How is this deployed?" | `trace_deployment_chain` |
| "What provisions this database?" | `trace_resource_to_code` |
| "Compare prod and staging" | `compare_environments` |
| "What does this repo contain?" | `get_repo_context` |
| "Tell me the Internet-to-cloud-to-code story for this repo" | `get_repo_story` |
| "Tell me the deployment story for this workload or service" | `get_workload_story`, `get_service_story` |
| "Explain this service, then cite the relevant files and docs" | `get_service_story` followed by `get_file_content`, `get_file_lines`, `search_file_content` |
| "Create support or onboarding documentation for this repo or service" | `get_repo_story`, `get_service_story`, `get_workload_story` |
| "Show me the source of this file" | `get_file_content` |
| "Search across indexed code" | `search_file_content` |
| "Find complex functions" | `find_most_complex_functions` |
| "What's dead code?" | `find_dead_code` |

## Story-first responses

For repository and deployment questions, PCG now exposes dedicated story surfaces:

- `get_repo_story`
- `get_workload_story`
- `get_service_story`

Use it this way:

1. start with `story`
2. use `story_sections` for grouped supporting context
3. use `deployment_overview`, `gitops_overview`, `documentation_overview`, or `support_overview` for structured evidence
4. if the answer needs exact file or docs evidence, follow with Postgres-backed content reads or search
5. use `drilldowns` to move into `get_repo_context`, `get_workload_context`, `get_service_context`, `trace_deployment_chain`, content reads, or lower-level relationship tools

This keeps answers concise without hiding the underlying evidence.

For documentation-oriented answers, the orchestration order is:

1. graph-first story and context
2. structured GitOps, documentation, and support overviews
3. targeted Postgres file reads or content search
4. exact file or line citations only when the story answer needs them

The current story order is:

1. public entrypoints
2. API surface
3. deployment path
4. runtime or platform context
5. shared config families and consumer context
6. limitation notes and coverage gaps

`deployment_story` usually comes from explicit delivery paths. When those are missing, PCG next tries to synthesize a truthful delivery path from reusable-workflow handoff plus canonical deploy/provision/runtime context. Only after that does it fall back to controller/runtime evidence such as Terraform, CodeDeploy, runtime platforms, and service variants.

There is now a controller-driven automation tier between those two extremes. For example, if a repo is deployed through Jenkins invoking Ansible, PCG can surface that as story-first context through `controller_driven_paths` even when GitHub Actions style delivery rows are absent. Consume that layer in this order:

1. `story`
2. `story_sections`
3. `deployment_overview`
4. `delivery_paths`
5. `controller_driven_paths`
6. detailed evidence fields

For programming prompts, keep using the code-query tools directly:

- `find_code`
- `analyze_code_relationships`
- `calculate_cyclomatic_complexity`
- `find_most_complex_functions`
- `find_dead_code`

Those remain the primary public contract for callers/callees/class hierarchy/import/complexity/dead-code questions. The story tools are for end-to-end narratives, not a replacement for the code tools.

## Repository access handoff

When PCG is deployed remotely, the server may not have local access to every repository. Content retrieval follows a fallback chain:

1. **PostgreSQL content store** — preferred, fastest
2. **Server workspace** — shared checkout volume
3. **Graph cache** — metadata stored during indexing
4. **Conversational handoff** — asks the user for a local path

Read responses include `source_backend` so you know where the answer came from. On stdio MCP clients that support elicitation, PCG can prompt for a local checkout path directly through the protocol. On HTTP clients, it falls back to conversational handoff.

`search_file_content` and `search_entity_content` require the PostgreSQL content store — they do not fall back to workspace scanning.

For documentation and runbook generation, expect the story layer to prefer Postgres-backed content evidence whenever it needs exact docs, README, runbook, overlay, or config references. If content is missing, story responses should expose limitations instead of implying the docs do not exist.

## Prompt-suite guardrails

Prompt-suite coverage should stay portable and auth-safe:

- use repo-relative identifiers and paths, not server-local filesystem paths
- prefer story and context tools before raw content search when the user asks for explanation or documentation
- use Postgres-backed content reads and search as evidence fetchers after the story identifies the right artifacts
- prefer structured MCP or HTTP tools before any expert fallback
- do not treat raw Cypher as a generic fallback for prompt or story tests
- only ask for a local checkout path when a workflow truly needs the user's machine

These rules keep prompt tests from leaking server paths or normalizing unsafe query habits into the public surface.

## Troubleshooting

**"Tool not found"** — verify the MCP server is running (`pcg mcp start`) and your client config points to the correct command or URL.

**"No repositories indexed"** — MCP queries the graph, which requires indexing first. Run `pcg index /path/to/repo` or start docker-compose to index fixtures.

**Slow responses** — large graphs on FalkorDB Lite may hit memory limits. Switch to Neo4j for production-scale graphs.

## Related docs

- [Starter Prompts](starter-prompts.md) — role-based prompt examples you can use immediately
- [MCP Reference](../reference/mcp-reference.md) — full tool list with parameters
- [MCP Cookbook](../reference/mcp-cookbook.md) — detailed query examples
- [HTTP API](../reference/http-api.md) — automation and service-to-service access
- [Shared Infra Trace](shared-infra-trace.md) — cross-repo infrastructure tracing
