# Decoupled Runtime Indexing Design

## Goal

Make PlatformContextGraph resilient to GitHub, DNS, parser, and checkpoint failures by removing full-reindex bootstrap from the pod startup path and treating repository sync plus indexing as resumable background work.

## Background

The current `ops-qa` incidents all share the same structural weakness: the service pod cannot start until bootstrap completes, and bootstrap currently does all of the following in one init-container path:

- acquire the shared workspace lock
- mint a GitHub App installation token
- discover repositories from GitHub
- clone or fetch repositories into the shared workspace
- index the workspace
- finalize graph state

That means any transient failure in GitHub DNS resolution, GitHub API availability, rate limiting, repository cloning, parser behavior, or checkpoint serialization keeps the entire pod in `Init:*` and prevents the HTTP API and MCP service from starting.

The recent failures have included:

- stale workspace locks causing bootstrap and `repo-sync` to skip work
- parser and YAML degradation during large legacy-repo runs
- repo-level persistence bugs (`PosixPath` JSON serialization, missing content-store delete method)
- missing runtime grammar packages
- transient `api.github.com` DNS failures while minting GitHub App tokens

These were different symptoms of the same design problem: indexing is treated as a hard startup prerequisite instead of a durable background subsystem.

## Requirements

- The HTTP API and MCP service must be able to start when the application’s own dependencies are healthy, even if GitHub is temporarily unavailable.
- Repository sync and indexing must be resumable at repo granularity and must survive pod restarts.
- Bootstrap and `repo-sync` must share one durable run/checkpoint model.
- A transient GitHub or DNS failure must not force the whole pod into a long init crash loop.
- The system must clearly distinguish service health from indexing progress.
- Logs, metrics, and traces must make it obvious whether the system is healthy, partially indexed, retrying, or blocked.
- One bad repository or file must not stop unrelated repositories from being indexed.

## Non-Goals

- Per-file checkpointing. Repository-level recovery is sufficient for the first version.
- Eliminating all parser warnings. The immediate requirement is graceful degradation and classification.
- Exposing external Bolt for Neo4j administration. This design is about indexing/runtime behavior.
- Replacing GitHub App authentication or adding a new control plane service.

## Constraints

- The current source repo already contains a resumable repo-batch coordinator under `src/platform_context_graph/indexing/`.
- The deployment currently runs bootstrap as an init container in the Helm chart and ArgoCD application.
- Neo4j and Postgres remain the persistence targets for indexed data.
- Shared workspace state already lives on PVC-backed disk, so checkpoint durability can remain disk-backed.

## Approaches Considered

### 1. Keep init-container bootstrap and add more retries

Add retries, backoff, and token caching to the current init flow, but keep full indexing in startup.

**Pros**

- Smallest code change.
- Fastest path to reduce the current outage frequency.

**Cons**

- Still blocks the app on external dependencies.
- Still couples service availability to indexing duration.
- Still makes every startup a large blast-radius event.

### 2. Move bootstrap into a separate Kubernetes Job

Run clone/index/finalization in a Job and let the app pod start independently.

**Pros**

- Better isolation than init containers.
- Preserves the idea of a “bootstrap run.”

**Cons**

- Creates split ownership between Job state and `repo-sync`.
- Still leaves checkpointing, retry policy, and status reporting fragmented.
- Adds deployment coordination without fixing the runtime model.

### 3. Treat sync and indexing as first-class background workers

Start the API independently, run repository acquisition and indexing as resumable background work using the shared coordinator and explicit status surfaces.

**Pros**

- Correct failure domain.
- Aligns with the existing resumable coordinator design already in the codebase.
- Makes transient external failures degrade freshness instead of service availability.
- Gives clean semantics for retries, resume, per-repo failure isolation, and observability.

**Cons**

- Requires both source and deployment changes.
- Requires careful status/health design so operators understand partial-index states.

## Chosen Approach

Approach 3.

The service will no longer depend on successful repository bootstrap during pod startup. Instead:

- the API/MCP container starts when app-local dependencies are healthy
- repository acquisition runs in a background runtime mode
- indexing runs through the resumable repo-batch coordinator
- progress, retries, partial failures, and last-success information become explicit status surfaces

## Target Architecture

### 1. API service

The API container owns only service availability:

- start FastAPI and MCP transport
- validate local runtime dependencies
- expose health and indexing-status endpoints

The API must not wait for GitHub discovery, cloning, or indexing completion before reporting healthy.

### 2. Repository sync worker

The sync runtime owns:

- GitHub App token acquisition and reuse
- repository discovery
- clone/fetch/update behavior
- workspace lock ownership
- repo acquisition status per repository

This worker must classify failures instead of collapsing them into one generic crash:

- transient DNS/network
- HTTP rate limit / abuse limit
- authentication / credential error
- repository clone/fetch error

### 3. Indexing worker

The indexing runtime owns:

- repo-level parse and snapshot creation
- repo-scoped commit into Neo4j and Postgres
- repair of `commit_incomplete` repositories
- batch finalization

This worker already maps well to the existing `execute_index_run(...)` coordinator model and should become the canonical path for both bootstrap and `repo-sync`.

### 4. Durable run state

The shared checkpoint model must become the system of record for runtime progress:

- run status
- per-repo status
- last error
- pending/completed/failed counts
- finalization status
- retry state for sync-side external dependency failures

That state remains disk-backed under `PCG_HOME`, not Redis or Postgres.

## Failure Model

### Service health

`/health` means:

- the service process is up
- core app dependencies are initialized enough to serve requests

It does **not** mean:

- all repositories are indexed
- GitHub is reachable
- the latest sync cycle succeeded

### Indexing health

A separate indexing-status surface must describe:

- active run id
- mode (`bootstrap`, `sync`, `manual`)
- run status
- finalization status
- completed / failed / pending repo counts
- last successful run timestamp
- last error
- whether the system is currently serving partial data

### Failure isolation

- file-level parse issues become warnings/evidence, not process failures
- repo-level failures mark only that repo failed
- cross-store commit failures become `commit_incomplete`
- transient external failures back off and retry without crashing the app container

## Defensive Measures

### GitHub API resilience

- add bounded retries with jitter for transient request failures
- classify DNS/network errors separately from HTTP rate limiting
- cache GitHub App installation tokens until close to expiry
- on 403/429, honor rate-limit/reset semantics instead of restart-looping

### Lock resilience

- keep heartbeat-backed workspace ownership
- distinguish live lock owner from stale lock owner
- bootstrap must wait or attach to current run state, not silently skip as success
- `repo-sync` may skip a cycle when the workspace is actively owned, but that skip must be explicit in logs and telemetry

### Telemetry correctness

- do not record `indexed` before commit succeeds
- emit per-repo start/completion/failure metrics only after state transition
- add run-level and repo-level OTEL spans for sync, checkpoint load/save, retries, and finalization

### Parser and content resilience

- use tolerant source decoding and permissive YAML handling
- record warnings with file path and failure class
- continue processing the rest of the repository when possible
- capture disappearing-file races as non-fatal parse degradations

## Deployment Model

The rollout should move from “blocking init bootstrap” to “background runtime” in two stages:

### Stage 1: Hardening within the current deployment

- keep current deployment shape
- add retry/backoff and token caching
- fix telemetry correctness
- add indexing-status visibility

This reduces outages immediately.

### Stage 2: Remove indexing from the init-container critical path

- start the app independently of full indexing completion
- move bootstrap into the long-lived runtime path or a coordinated background worker
- keep PVC-backed workspace and checkpoint storage

This is the structural fix.

## Validation

- Unit tests for transient GitHub failures, rate-limit handling, and token caching.
- Unit tests for lock contention, stale lock reaping, and bootstrap wait behavior.
- Unit tests for checkpoint state transitions and repo-level recovery.
- Integration tests proving the API starts while indexing is pending or partially failed.
- Live verification in `ops-qa` that:
  - the API comes up without waiting on GitHub success
  - indexing retries through transient GitHub failure
  - partial indexing is visible through status surfaces
  - `repo-sync` and bootstrap use the same durable run model
