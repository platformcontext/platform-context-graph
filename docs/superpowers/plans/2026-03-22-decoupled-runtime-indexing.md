# Decoupled Runtime Indexing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove GitHub- and indexing-related startup fragility by decoupling service readiness from bootstrap indexing, hardening repo sync against transient external failures, and making runtime progress explicit through resumable state plus status surfaces.

**Architecture:** Keep the existing repo-batch indexing coordinator as the core execution engine, but harden the repo-sync/bootstrap side so GitHub token minting, repository discovery, clone/fetch, and workspace locking become resilient background work instead of pod-startup blockers. Service health stays tied to the API process, while indexing freshness moves behind explicit status APIs, metrics, and runtime logs.

**Tech Stack:** Python, FastAPI, Neo4j, Postgres, OpenTelemetry, pytest, Helm, ArgoCD, Kubernetes

---

## Chunk 1: Immediate Runtime Hardening

### Task 1: Finish the transient GitHub failure protections in the runtime path

**Files:**
- Modify: `src/platform_context_graph/runtime/repo_sync/git.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/bootstrap.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/support.py`
- Test: `tests/unit/runtime/test_repo_sync_runtime.py`

- [ ] **Step 1: Write or extend failing runtime tests**
Cover these cases explicitly:
  - GitHub App token minting retries transient `requests`/DNS failures before failing.
  - bootstrap waits for the workspace lock instead of treating lock contention as success.
  - stale lock metadata is reaped and bootstrap proceeds.

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py -q`
Expected: FAIL before implementation on the retry and lock-wait cases.

- [ ] **Step 3: Implement the minimal resilience fix**
In `git.py`:
  - route GitHub API calls through one retrying helper
  - classify request failures as retriable/non-retriable
  - keep logs specific enough to distinguish DNS/network from HTTP failures

In `bootstrap.py`:
  - retry lock acquisition for init-container bootstrap
  - fail non-zero when bootstrap cannot acquire the lock in time

In `support.py`:
  - keep heartbeat-backed lock metadata and stale-lock reaping behavior
  - make lock acquire/skip/release logs explicit

- [ ] **Step 4: Re-run the runtime suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py -q`
Expected: PASS.

### Task 2: Add GitHub token caching and explicit rate-limit handling

**Files:**
- Create: `src/platform_context_graph/runtime/repo_sync/github_auth.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/git.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/config.py`
- Test: `tests/unit/runtime/test_repo_sync_runtime.py`

- [ ] **Step 1: Add failing auth-behavior tests**
Cover:
  - cached installation token reused until close to expiry
  - `403`/`429` rate-limit responses are classified separately from DNS/network failures
  - runtime backs off using reset/retry information instead of hammering GitHub

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py -k "github or token or rate" -q`
Expected: FAIL before implementation.

- [ ] **Step 3: Implement token caching and rate-limit behavior**
Add a small, focused auth helper that:
  - caches the active GitHub App installation token with expiry metadata
  - refreshes only when the token is near expiry
  - surfaces rate-limit/reset data in logs and telemetry
  - exposes one narrow API used by the repo-sync runtime

- [ ] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py -k "github or token or rate" -q`
Expected: PASS.

## Chunk 2: Correct Status and Telemetry Semantics

### Task 3: Stop reporting optimistic indexing success

**Files:**
- Modify: `src/platform_context_graph/runtime/repo_sync/bootstrap.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/sync.py`
- Modify: `src/platform_context_graph/observability/runtime.py`
- Modify: `src/platform_context_graph/observability/metrics.py`
- Test: `tests/unit/runtime/test_repo_sync_runtime.py`
- Test: `tests/unit/tools/test_graph_builder_indexing_execution.py`

- [ ] **Step 1: Add failing telemetry tests**
Require:
  - `indexed` is recorded only after successful repo commit or successful batch completion
  - lock contention and external retry behavior emit explicit metrics without being counted as indexing success
  - repo-level completion/failure counts match persisted run state

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py tests/unit/tools/test_graph_builder_indexing_execution.py -q`
Expected: FAIL where optimistic `indexed` metrics are still emitted.

- [ ] **Step 3: Implement telemetry corrections**
Update runtime telemetry so:
  - `discovered`, `cloned`, `updated`, `failed`, `resumed`, `commit_incomplete`, and `completed` reflect real transitions
  - `indexed` means successful indexed commit, not “we decided to start indexing”
  - lock-skipped and retrying states are logged and metered explicitly

- [ ] **Step 4: Re-run the telemetry suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py tests/unit/tools/test_graph_builder_indexing_execution.py -q`
Expected: PASS.

### Task 4: Surface indexing state as a first-class API/CLI status

**Files:**
- Modify: `src/platform_context_graph/indexing/coordinator.py`
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Modify: `src/platform_context_graph/cli/commands/basic.py`
- Modify: `src/platform_context_graph/api/app.py`
- Create: `src/platform_context_graph/api/routers/status.py`
- Modify: `src/platform_context_graph/api/routers/__init__.py`
- Test: `tests/unit/indexing/test_coordinator_storage.py`
- Create: `tests/integration/api/test_status_api.py`

- [ ] **Step 1: Add failing status-surface tests**
Require:
  - `pcg index-status <path>` reports latest run id, status, finalization status, pending/completed/failed counts, and last error
  - HTTP `/api/v0/index-status` (or equivalent route) returns the same information
  - `/health` remains simple service health and does not imply indexing completeness

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/indexing/test_coordinator_storage.py tests/integration/api/test_status_api.py -q`
Expected: FAIL before implementation.

- [ ] **Step 3: Implement explicit indexing-status surfaces**
Use `describe_latest_index_run(...)` from the coordinator as the data source and expose it through:
  - CLI status command
  - one API route for service operators

- [ ] **Step 4: Re-run the status suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/indexing/test_coordinator_storage.py tests/integration/api/test_status_api.py -q`
Expected: PASS.

## Chunk 3: Remove Full Bootstrap From the Pod Startup Critical Path

### Task 5: Make the service start independently of repository bootstrap completion

**Files:**
- Modify: `src/platform_context_graph/cli/commands/runtime.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/bootstrap.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/sync.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/config.py`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/chart/templates/statefulset.yaml`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/chart/values.yaml`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/argocd/platformcontextgraph/base/app-values.yaml`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/argocd/platformcontextgraph/overlays/ops-qa/app-values.yaml`
- Test: `tests/integration/deployment/test_public_deployment_assets.py`

- [ ] **Step 1: Write failing deployment/runtime tests**
Cover:
  - the app container can start without waiting for full bootstrap indexing
  - runtime commands still support an initial sync/index phase, but it no longer gates FastAPI startup via init container completion
  - rendered deployment assets no longer express the old “full bootstrap must succeed before app starts” contract

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q`
Expected: FAIL before deployment/runtime changes.

- [ ] **Step 3: Implement the startup decoupling**
Refactor runtime/deployment so:
  - the service container starts independently
  - repository sync/indexing run as background work
  - bootstrap semantics become “eventual initial catch-up,” not “hard startup gate”

- [ ] **Step 4: Re-run the deployment suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q`
Expected: PASS.

### Task 6: Keep resumable indexing as the single execution engine for runtime and manual CLI

**Files:**
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/bootstrap.py`
- Modify: `src/platform_context_graph/runtime/repo_sync/sync.py`
- Modify: `src/platform_context_graph/tools/graph_builder.py`
- Modify: `src/platform_context_graph/indexing/coordinator.py`
- Test: `tests/unit/cli/test_indexing_helper.py`
- Test: `tests/unit/runtime/test_repo_sync_runtime.py`

- [ ] **Step 1: Add failing integration-style unit tests**
Require:
  - manual `pcg index` and runtime repo indexing both route through the same coordinator semantics
  - force reindex invalidates the matching checkpoint
  - repo-sync indexes only changed/synced repos instead of treating the whole workspace as one opaque rerun

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/cli/test_indexing_helper.py tests/unit/runtime/test_repo_sync_runtime.py -q`
Expected: FAIL where runtime/manual paths still diverge.

- [ ] **Step 3: Implement the unification**
Route runtime and manual directory indexing through the same coordinator-backed contract:
  - repo discovery/acquisition state from runtime
  - repo-batch indexing and finalization from the coordinator
  - shared status reporting and failure semantics

- [ ] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/cli/test_indexing_helper.py tests/unit/runtime/test_repo_sync_runtime.py -q`
Expected: PASS.

## Chunk 4: End-to-End Validation and Ops Rollout

### Task 7: Verify parser/content degradation stays non-fatal under the new runtime

**Files:**
- Modify: `src/platform_context_graph/utils/source_text.py`
- Modify: `src/platform_context_graph/tools/languages/yaml_infra_support.py`
- Modify: `src/platform_context_graph/tools/graph_builder_indexing_execution.py`
- Test: `tests/unit/parsers/test_yaml_infra_parser.py`
- Test: `tests/unit/content/test_workspace.py`

- [ ] **Step 1: Add failing degradation tests for the remaining known classes**
Cover:
  - non-UTF8 legacy source files
  - disappearing files during pre-scan
  - malformed YAML with tabs
  - YAML with unknown tags such as `!vault`

- [ ] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/parsers/test_yaml_infra_parser.py tests/unit/content/test_workspace.py tests/unit/tools/test_graph_builder_indexing_execution.py -q`
Expected: FAIL where any of those still fail whole-repo or whole-run behavior.

- [ ] **Step 3: Implement or tighten per-file degradation handling**
Ensure those cases remain warnings/evidence and never become process-level failures.

- [ ] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/parsers/test_yaml_infra_parser.py tests/unit/content/test_workspace.py tests/unit/tools/test_graph_builder_indexing_execution.py -q`
Expected: PASS.

### Task 8: Build, deploy, and verify the resilient runtime in `ops-qa`

**Files:**
- Modify: source files from prior tasks
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/chart/Chart.yaml`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/chart/values.yaml`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/argocd/platformcontextgraph/base/app-values.yaml`
- Modify: `/Users/allen/repos/mobius/iac-eks-pcg/argocd/platformcontextgraph/overlays/ops-qa/app-values.yaml`

- [ ] **Step 1: Run the source verification gate**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/runtime/test_repo_sync_runtime.py tests/unit/cli/test_indexing_helper.py tests/unit/indexing/test_coordinator_storage.py tests/unit/content/test_postgres.py tests/unit/parsers/test_yaml_infra_parser.py tests/unit/tools/test_graph_builder_indexing_execution.py tests/integration/api/test_status_api.py tests/integration/deployment/test_public_deployment_assets.py -q`
  - `python3 scripts/check_python_docstrings.py`
  - `python3 scripts/check_python_file_lengths.py --max-lines 500`
Expected: PASS.

- [ ] **Step 2: Build and publish the next runtime image**
Run:
  - `docker buildx build --platform linux/amd64,linux/arm64 -t boatsgroup.pe.jfrog.io/bg-docker/platformcontextgraph:<new-tag> --push .`
  - `docker manifest inspect boatsgroup.pe.jfrog.io/bg-docker/platformcontextgraph:<new-tag>`
Expected: multi-arch image published successfully.

- [ ] **Step 3: Update the deploy repo and merge the release PR**
Update the image tag in `iac-eks-pcg`, push a branch, and open the PR.

- [ ] **Step 4: Verify live rollout behavior**
Run:
  - `kubectl --context ops-qa get application -n argocd platformcontextgraph-ops-qa`
  - `kubectl --context ops-qa get pods -n platformcontextgraph -o wide`
  - `kubectl --context ops-qa logs -n platformcontextgraph pod/platformcontextgraph-0 -c platform-context-graph --tail=200`
  - `kubectl --context ops-qa logs -n platformcontextgraph pod/platformcontextgraph-0 -c repo-sync --tail=200`
  - `curl -sk https://mcp-pcg.qa.ops.bgrp.io/health`
  - `curl -sk https://mcp-pcg.qa.ops.bgrp.io/api/v0/index-status`
Expected:
  - API starts without waiting on full indexing success
  - sync/index retries are visible in logs instead of crash-looping the pod
  - status endpoint reports indexing progress and any partial failures
  - repo-sync logs are visible even when indexing is still catching up

- [ ] **Step 5: Validate real user-facing behavior**
Run a real MCP prompt against the live QA endpoint and confirm:
  - repository context tools return partial-but-valid data when indexing is incomplete
  - tool errors distinguish “not indexed yet” from “service unavailable”
  - transient GitHub failure no longer takes the whole service offline

- [ ] **Step 6: Commit in small slices**
Use frequent commits by task or chunk instead of one large “runtime redesign” commit.
