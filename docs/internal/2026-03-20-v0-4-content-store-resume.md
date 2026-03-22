# v0.4 Content Store Resume

## Status

Paused for host reboot.

Implementation status is effectively **6 of 7 major workstreams complete**:

1. Content-provider layer: complete
2. Postgres schema and dual-write ingest: complete
3. HTTP and MCP content surfaces: complete
4. Remote-first portable content identity: complete
5. Repo-sync rediscovery and repository rules: complete
6. Deployment, observability, and docs wiring: complete
7. Fresh-volume live verification and final regression sweep: remaining

## What Was Completed

- Added Postgres-backed content storage and workspace fallback under `src/platform_context_graph/content/`.
- Added query-layer content services in `src/platform_context_graph/query/content.py`.
- Added HTTP content routes in `src/platform_context_graph/api/routers/content.py`.
- Added MCP content tools in `src/platform_context_graph/mcp/content_tools.py` and `src/platform_context_graph/mcp/tools/content.py`.
- Dual-write indexing now persists `content_files` and `content_entities`.
- Repo-sync already rediscovered repos each cycle; this pass confirmed and extended rule coverage plus stale-checkout telemetry.
- Added content-provider observability metrics and deployment wiring for Postgres + repository rules.
- Updated README and docs for content retrieval, external Postgres, repository rules, and deployment shape.
- Fixed two live local-runtime bugs discovered during compose verification:
  - repository merge now adopts existing path-keyed `Repository` nodes instead of tripping the `Repository.path` uniqueness constraint
  - bootstrap idempotency now counts descendant files with `[:CONTAINS*]->(f:File)` so a workspace root is not incorrectly treated as empty

## Important Current State

- No commit has been made.
- The compose stack was intentionally torn down with `docker-compose down -v`.
- At pause time, **all compose-managed volumes were removed** so the next run starts from a clean Neo4j/Postgres/workspace state.
- Docker/Colima was restarted successfully before the pause.

## Last Known Good Checks

- Targeted content and deployment tests passed.
- Docs build passed with `mkdocs build --strict`.
- The repository and bootstrap idempotency bug fixes both have focused tests.

## Immediate Next Steps After Reboot

1. Start Docker/Colima if needed.
2. Bring up the clean local stack:

   ```bash
   cd /Users/allen/personal-repos/platform-context-graph
   docker-compose up -d --build
   ```

3. Verify containers and bootstrap:

   ```bash
   docker-compose ps
   docker-compose logs --tail=200 bootstrap-index
   docker-compose logs --tail=200 repo-sync
   docker-compose logs --tail=200 platform-context-graph
   ```

4. Verify live endpoints:

   ```bash
   curl -fsS http://localhost:8080/health
   curl -fsS http://localhost:8080/api/v0/repositories
   ```

5. Exercise at least one content route against clean fixture data:

   ```bash
   curl -fsS http://localhost:8080/api/v0/openapi.json >/tmp/pcg-openapi.json
   ```

   Then choose a real `repo_id` and `relative_path` from the indexed fixture repos and test:

   - `POST /api/v0/content/files/read`
   - `POST /api/v0/content/files/lines`
   - `POST /api/v0/content/entities/read`

6. Run the final repo guards:

   ```bash
   python3 scripts/check_python_file_lengths.py --max-lines 500
   python3 scripts/check_python_docstrings.py
   ```

7. Run the final broad verification sweep:

   ```bash
   PYTHONPATH=src uv run python -m pytest tests/unit tests/integration/api tests/integration/mcp/test_mcp_server.py tests/integration/cli/test_cli_commands.py tests/integration/docs tests/integration/deployment/test_public_deployment_assets.py -q
   uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
   ```

## Files Most Relevant To Resume

- `src/platform_context_graph/content/`
- `src/platform_context_graph/query/content.py`
- `src/platform_context_graph/api/routers/content.py`
- `src/platform_context_graph/mcp/content_tools.py`
- `src/platform_context_graph/tools/graph_builder_persistence.py`
- `src/platform_context_graph/cli/helpers/indexing.py`
- `src/platform_context_graph/runtime/repo_sync/`
- `docker-compose.yaml`
- `deploy/helm/platform-context-graph/values.yaml`
- `tests/integration/api/test_content_api.py`
- `tests/integration/mcp/test_content_tools.py`

