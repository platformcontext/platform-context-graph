# Testing

PlatformContextGraph uses a layered test strategy:

- unit tests for graph/query logic
- integration tests for CLI, MCP, and HTTP API contracts
- deployment tests for Helm, manifests, and Compose assets
- end-to-end tests for realistic user journeys

## Core Commands

Fast local pass:

```bash
./tests/run_tests.sh fast
```

Focused API + query verification:

```bash
PYTHONPATH=src uv run python -m pytest tests/unit/query tests/integration/api tests/integration/mcp/test_mcp_server.py -q
```

Deployment asset verification:

```bash
PYTHONPATH=src uv run python -m pytest tests/integration/deployment/test_public_deployment_assets.py -q
helm template platform-context-graph ./deploy/helm/platform-context-graph
kubectl kustomize deploy/manifests/minimal
```

Docs smoke tests:

```bash
PYTHONPATH=src uv run python -m pytest tests/integration/docs/test_docs_smoke.py -q
```

## Local Service Stack

The repository ships a Docker Compose harness that mirrors the production lifecycle:

1. start Neo4j
2. bootstrap index fixture repos
3. start the combined HTTP API + MCP service
4. run ongoing repo sync

The bootstrap and repo-sync containers both execute the internal Python runtime commands, not shell-based sync scripts.

Run it with:

```bash
docker compose up --build
```

If the default host ports are already in use locally, override them:

```bash
NEO4J_HTTP_PORT=17474 \
NEO4J_BOLT_PORT=17687 \
PCG_HTTP_PORT=18080 \
docker compose up --build
```

The fixture ecosystems used by that stack live under `tests/fixtures/ecosystems`.

## What We Verify

- query contracts and graph reasoning
- CLI behavior and flags
- MCP routing and tool exposure
- HTTP API and OpenAPI contract stability
- deployment artifacts for the public chart and minimal manifests
- shared-infra scenarios such as one resource supporting multiple workloads

## Current Gaps

- no full Kubernetes cluster integration test yet
- no automated EKS smoke test yet
- the compose-backed deployable-service flow should continue to grow with richer fixture ecosystems
