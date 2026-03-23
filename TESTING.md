# Testing

PlatformContextGraph uses a layered test strategy:

- **Unit tests** for parser extraction and query logic
- **Integration tests** for CLI, MCP, and HTTP API contracts
- **Deployment tests** for Helm, manifests, and Compose assets
- **End-to-end tests** for realistic user journeys through the full stack

## Quick Start

Fast local pass (unit + deployment):

```bash
./tests/run_tests.sh fast
```

## Layer Breakdown

### Unit tests

Parser extraction, query logic, domain models. No external services needed.

```bash
./tests/run_tests.sh unit
```

### Integration tests

Graph persistence, API contracts, MCP routing, CLI behavior. Requires Neo4j.

```bash
PYTHONPATH=src uv run python -m pytest tests/unit/query tests/integration/api tests/integration/mcp/test_mcp_server.py -q
```

### Deployment asset tests

Helm templates, Kustomize manifests, Compose config. No external services needed.

```bash
PYTHONPATH=src uv run python -m pytest tests/integration/deployment/test_public_deployment_assets.py -q
helm template platform-context-graph ./deploy/helm/platform-context-graph
kubectl kustomize deploy/manifests/minimal
```

### Docs smoke tests

```bash
PYTHONPATH=src uv run python -m pytest tests/integration/docs/test_docs_smoke.py -q
```

## Local Service Stack

The Docker Compose stack mirrors the production lifecycle:

1. Start Neo4j and Postgres
2. Bootstrap-index fixture repos
3. Start the combined HTTP API + MCP service
4. Run ongoing repo sync

```bash
docker compose up --build
```

If the default ports are in use:

```bash
NEO4J_HTTP_PORT=17474 \
NEO4J_BOLT_PORT=17687 \
PCG_HTTP_PORT=18080 \
docker compose up --build
```

The fixture ecosystems used by the stack live under `tests/fixtures/ecosystems/`.

## What We Verify

- Query contracts and graph reasoning
- CLI behavior and flags
- MCP routing and tool exposure
- HTTP API and OpenAPI contract stability
- Deployment artifacts for the public chart and minimal manifests
- Shared-infra scenarios (one resource supporting multiple workloads)

## Current Gaps

- No full Kubernetes cluster integration test yet
- No automated EKS smoke test yet
- The Compose-backed service flow should continue to grow with richer fixture ecosystems
