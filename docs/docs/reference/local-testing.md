# Local Testing Runbook

This is the default local verification runbook for engineers, Claude, and Codex.

Use it to answer:

- Which commands should I run for this kind of change?
- What is the minimum acceptable verification before I call work ready?
- How do I run the three-service stack locally?
- How do I validate the facts-first pipeline and telemetry path?

## Default Rule

Run the smallest test set that proves the change, then run the deployment/docs
checks required by the surfaces you touched.

Do not claim a change is ready without citing the commands you actually ran.

## Common Environment

When running directly against a local Docker Compose stack:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PYTHONPATH=src
```

## Quick Verification Matrix

| If you touched | Minimum verification |
| --- | --- |
| Docs, `CLAUDE.md`, `AGENTS.md`, or README files | `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml` |
| CLI/runtime wiring | `PYTHONPATH=src uv run pytest tests/integration/cli/test_cli_commands.py -q` |
| Compose, Helm, or deployable runtime shape | `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q` and `helm lint deploy/helm/platform-context-graph` |
| Facts-first indexing, queue, or resolution flow | `PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_git_facts_end_to_end.py tests/integration/indexing/test_git_facts_projection_parity.py -q` |
| Phase 3 recovery controls (`admin_facts`, queue recovery helpers, replay events, backfill) | `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_recovery.py tests/unit/api/test_admin_facts_recovery_router.py tests/integration/cli/test_remote_cli.py -q` |
| Facts-first telemetry or queue scaling | `PYTHONPATH=src:. uv run pytest tests/unit/observability/test_fact_resolution_telemetry.py tests/unit/observability/test_fact_runtime_scaling_telemetry.py tests/unit/observability/test_resolution_queue_sampler.py tests/unit/observability/test_facts_first_logging.py -q` |
| Admin replay flow | `PYTHONPATH=src uv run pytest tests/integration/api/test_admin_facts_replay.py tests/integration/cli/test_admin_facts_replay_cli.py -q` |
| Python file layout/quality gates | `python3 scripts/check_python_file_lengths.py --max-lines 500` and `git diff --check` |

## Local Three-Service Stack

Start the full stack:

```bash
docker compose up --build
```

This brings up:

- Neo4j
- Postgres
- OTEL collector
- Jaeger
- `bootstrap-index`
- `platform-context-graph` API
- `repo-sync`
- `resolution-engine`

Useful checks:

```bash
docker compose ps
docker compose logs bootstrap-index | tail -50
docker compose logs repo-sync | tail -50
docker compose logs resolution-engine | tail -50
curl -s http://localhost:8080/health
```

Telemetry endpoints:

- Jaeger UI: `http://localhost:16686`
- Collector Prometheus metrics: `http://localhost:9464/metrics`

## Recommended Test Order

### 1. Smallest targeted test first

Run the most local unit or integration suite that covers the code you touched.

### 2. Deployment contract if runtime shape changed

If you touched Compose, Helm, entrypoints, or runtime-role wiring:

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q
helm lint deploy/helm/platform-context-graph
```

### 3. Facts-first parity if indexing changed

If you touched `facts/`, `resolution/`, `indexing/`, `collectors/`, `graph/`, or
runtime orchestration:

```bash
PYTHONPATH=src:. uv run pytest \
  tests/integration/indexing/test_git_facts_end_to_end.py \
  tests/integration/indexing/test_git_facts_projection_parity.py -q
```

### 4. Telemetry validation if observability changed

If you touched `observability/`, queue metrics, fact-store SQL telemetry, logs, or
OTEL wiring:

```bash
PYTHONPATH=src:. uv run pytest \
  tests/unit/observability/test_fact_resolution_telemetry.py \
  tests/unit/observability/test_fact_runtime_scaling_telemetry.py \
  tests/unit/observability/test_resolution_queue_sampler.py \
  tests/unit/observability/test_facts_first_logging.py -q
```

### 5. Recovery and admin validation if Phase 3 controls changed

If you touched queue recovery, replay/backfill controls, admin facts routers, or
remote CLI operator flows:

```bash
PYTHONPATH=src:. uv run pytest \
  tests/unit/facts/test_fact_work_queue_recovery.py \
  tests/unit/api/test_admin_facts_recovery_router.py \
  tests/integration/cli/test_remote_cli.py -q
```

### 6. Docs build if docs or instruction files changed

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Full Local Smoke For Release Candidates

Use this when a branch is close to merge or when the change affects multiple
runtime boundaries.

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q
PYTHONPATH=src uv run pytest tests/integration/cli/test_cli_commands.py -q
PYTHONPATH=src:. uv run pytest \
  tests/integration/indexing/test_git_facts_end_to_end.py \
  tests/integration/indexing/test_git_facts_projection_parity.py -q
PYTHONPATH=src:. uv run pytest \
  tests/unit/observability/test_fact_resolution_telemetry.py \
  tests/unit/observability/test_fact_runtime_scaling_telemetry.py \
  tests/unit/observability/test_resolution_queue_sampler.py \
  tests/unit/observability/test_facts_first_logging.py -q
PYTHONPATH=src:. uv run pytest \
  tests/unit/facts/test_fact_work_queue_recovery.py \
  tests/unit/api/test_admin_facts_recovery_router.py \
  tests/integration/cli/test_remote_cli.py -q
python3 scripts/check_python_file_lengths.py --max-lines 500
git diff --check
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## IaC Validation When Deployment Repo Changes Too

If the app change requires updates in `iac-eks-pcg`, also run there:

```bash
helm lint chart/ \
  -f argocd/platformcontextgraph/base/app-values.yaml \
  -f argocd/platformcontextgraph/overlays/ops-qa/app-values.yaml

helm template platformcontextgraph chart/ \
  -f argocd/platformcontextgraph/base/app-values.yaml \
  -f argocd/platformcontextgraph/overlays/ops-qa/app-values.yaml >/tmp/pcg-chart.yaml

kubectl kustomize argocd/platformcontextgraph/overlays/ops-qa >/tmp/pcg-kustomize.yaml
```

## Agent Completion Gate

Before Claude or Codex says a change is ready:

1. Identify the changed surface area.
2. Run the matching checks from this page.
3. Report the exact commands run.
4. Report anything not run.
5. Do not substitute “looks correct” for verification output.
