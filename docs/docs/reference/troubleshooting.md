# Troubleshooting

Use this page when CLI commands, MCP startup, the HTTP API, or the graph backend do not behave as expected.

## 1. `pcg` is not on PATH

Cause:

- the installation completed, but the scripts directory is not on your PATH

Fix:

- macOS / Linux: add the relevant scripts directory to your shell profile
- Windows: reinstall Python with PATH enabled, or prefer `uv tool install` / `pipx`

## 2. Neo4j connection refused

Cause:

- Neo4j is not running
- the URI is wrong
- the service is not reachable from the runtime environment

Fix:

```bash
docker start pcg-neo4j
```

Then verify your configured `NEO4J_URI`, username, and password.

## 3. MCP client cannot find the server

Cause:

- the client config was not updated correctly
- the configured command points at the wrong interpreter or virtualenv
- the database credentials are unavailable to the runtime

Fix:

- rerun `pcg mcp setup`
- inspect the generated config snippet
- run `pcg mcp start` manually and confirm it starts cleanly

For this repository's checked-in local setup, the MCP client should shell into the
running Compose service with `docker-compose exec -T platform-context-graph pcg mcp
start`. A host-run `uv run ... pcg mcp start` process with only Neo4j credentials
can answer graph queries, but the content tools will fail because the PostgreSQL
content-store DSN and the container workspace mounts are missing from that runtime.

## 4. The HTTP API starts but queries fail

Cause:

- the service can start without a meaningful graph loaded
- the repository was never indexed
- the entity ID is wrong or unresolved

Fix:

- confirm indexing completed
- inspect `GET /api/v0/repositories`
- resolve fuzzy inputs with `POST /api/v0/entities/resolve`

## 5. Hidden IaC cache directories are polluting the graph

PCG should skip hidden and ignored cache trees such as `.git`, `.terraform`, and `.terragrunt-cache` before descent.

If you suspect this is not happening:

- verify your ignore configuration
- re-index the repository with `pcg index <path> --force`
- inspect repository and file paths in the graph for hidden cache segments

## 6. Docker Compose or Kubernetes deployment is unhealthy

Check:

- Neo4j connectivity
- mounted workspace permissions
- bootstrap indexing completion
- repo-sync logs
- health endpoint readiness

## Getting help

If these do not solve the issue, open an issue on [GitHub](https://github.com/platformcontext/platform-context-graph/issues) with the output of `pcg doctor`.
