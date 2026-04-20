# ADR: Pre-Merge Validation — Local MCP Self-Indexing + IaC Chart Parity For Go Runtime

**Date:** 2026-04-20
**Status:** Proposed
**Authors:** Allen Sanabria
**Deciders:** Platform Engineering
**Related:**

- `2026-04-20-workflow-coordinator-and-multi-collector-runtime-contract.md`
- `2026-04-20-multi-source-reducer-and-consumer-contract.md`
- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/local-testing.md`
- `~/repos/mobius/iac-eks-pcg/chart/` (boats internal)

---

## Context

The `codex/go-data-plane-architecture` branch replaces the Python runtime with a
Go-only data plane:

- `pcg-api` (HTTP API Deployment)
- `pcg-mcp-server` (MCP transport, separate binary)
- `pcg-ingester` (StatefulSet, workspace PVC)
- `pcg-reducer` (resolution-engine Deployment)
- `pcg-workflow-coordinator` (new control-plane Deployment, dark by default)
- `pcg-bootstrap-data-plane` (bootstrap binary + compose/runtime helper; no
  Kubernetes rendering path in either chart today, see D2.7)
- `pcg-bootstrap-index` (one-shot helper)

Before merging this long-running branch into `main`, two claims must be
validated:

1. **The local stack indexes this repo and serves MCP to Claude Code well
   enough to reduce code-finding token cost.** PCG inherits CGC
   (CodeGraphContext) positioning; self-indexing is the minimum demo.
2. **The boats-internal IaC chart at `~/repos/mobius/iac-eks-pcg/` plus the
   `argocd/platformcontextgraph/overlays/ops-qa/` overlay deploys the new Go
   runtime correctly**, including the new workflow-coordinator workload and
   renamed env-var contract.

Both validations are research-only today. Execution (docker compose up, helm
template, kubectl apply) happens after this ADR is accepted.

---

## Decision

### D1 — Local MCP Self-Indexing Is A Pre-Merge Gate

Before `main` merge:

1. Run `docker compose up --build` with `PCG_FILESYSTEM_HOST_ROOT` pointing at a
   real directory that contains this repository (not a symlink; worktrees have
   a `.git` file pointer that the discovery path may skip — use the primary
   clone at `~/personal-repos/platform-context-graph`, or a fresh copy under
   `/Users/allen/pcg-local-index/`).
2. Run `./scripts/sync_local_compose_mcp.sh` so `.mcp.json` picks up the live
   mcp-server port and bearer token.
3. Confirm the pipeline reached steady state:
   - `curl -s http://localhost:8080/admin/status | jq .` — no failed work items
   - `curl -s http://localhost:8080/api/v0/repositories | jq '. | length'` — ≥1
4. Point Claude Code at the `pcg-local-compose` MCP entry and run a baseline
   set of queries against this repo:
   - `resolve_entity` on a known symbol (e.g. `DeployableUnitCorrelationHandler`)
   - `analyze_code_relationships` with `query_type: find_callers` on a
     reducer phase publisher (note: `find_callers` is not a standalone MCP
     tool — it is the enum value used inside `analyze_code_relationships`.
     See `go/internal/mcp/tools_codebase.go:52` for the full accepted enum)
   - repository-scoped content fetch
5. Record token-in / token-out for a matched MCP-assisted session vs. a
   Grep/Glob-only session on the same task.

Merge is not blocked on a specific token-savings threshold, but an honest
qualitative result ("MCP surfaced the handler directly" vs. "MCP returned
nothing useful") is required and should be captured in the merge PR body.

Known gotcha (carried from prior runs): if `.pcg-fixture-manifest` survives in
the `pcg_data` volume from a previous run, bootstrap skips discovery. Run
`docker compose down -v` between shape changes, or delete that manifest.

### D2 — IaC Chart Must Reach Parity With The Go Runtime Before ops-qa Deploy

The boats-internal chart at `~/repos/mobius/iac-eks-pcg/chart/` (v0.1.40,
appVersion `v0.0.58`) trails the upstream chart at
`deploy/helm/platform-context-graph/`. The following parity gaps MUST close
before this branch is merged and tagged for an ops-qa rollout.

#### D2.1 Missing templates

| Template | Upstream status | IaC status | Required for |
| --- | --- | --- | --- |
| `deployment-workflow-coordinator.yaml` | present | **missing** | new control plane (dark mode gate) |
| `service-workflow-coordinator.yaml` | present | **missing** | admin/metrics surface for coordinator |
| `networkpolicy.yaml` | present | **missing** | egress/ingress lockdown default |

Without the workflow-coordinator templates, the dark-by-default rollout has no
target to deploy to; the operator has no way to validate the coordinator
before turning on claim ownership.

#### D2.2 Missing values keys

IaC `chart/values.yaml` is missing:

- `workflowCoordinator:` block — required keys: `enabled` (default `false`),
  `deploymentMode: dark`, `claimsEnabled: false`, `collectorInstances: []`,
  `replicas`, `revisionHistoryLimit`, `connectionTuning`, `resources`.
- `connectionTuning:` blocks on `api`, `resolutionEngine`, and `ingester` for
  Postgres and Neo4j pool tuning — upstream supports all three.
- `networkPolicy.enabled` — default `true` per upstream.

Already present in IaC `chart/values.yaml` (do NOT re-add):

- `observability:` base block (lines 138–166) with `otel` + `prometheus`
  sub-blocks.
- `initContainerSecurityContext` (lines 29–37) with `runAsUser: 0` for DDL
  paths and `readOnlyRootFilesystem: true`.
- `podSecurityContext` / `containerSecurityContext` (lines 14–27).

The above correction supersedes any earlier draft wording that listed
`observability` or `initContainerSecurityContext` as missing — they are
present. The real gaps are the workflow-coordinator, connection-tuning, and
network-policy blocks.

#### D2.3 Helper functions

`chart/templates/_helpers.tpl` must define (or inherit) the helpers the new
upstream templates use:

- `pcg.renderConnectionTuningEnv`
- `pcg.renderOtelEnv`
- `pcg.renderPrometheusEnv`
- `pcg.workflowCoordinatorFullname`
- `pcg.workflowCoordinatorSelectorLabels`

Codex finding: IaC `deployment.yaml` already calls `pcg.renderOtelEnv` and
`pcg.renderPrometheusEnv` (line 65–66), so those helpers are present. The
coordinator-specific helpers and `pcg.renderConnectionTuningEnv` must be
added or back-ported.

#### D2.4 Environment variable drift — python-era keys still present

`chart/values.yaml env:` and the ops-qa overlay workload-specific env maps
(`app-values.yaml resolutionEngine.env:` and `app-values.yaml ingester.env:`)
contain keys the Go runtime does not read:

- `PCG_COMMIT_WORKERS`
- `PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED`
- `PCG_ASYNC_COMMIT_ENABLED`
- `PCG_FUNCTION_CALL_GLOBAL_FALLBACK`
- `PCG_CALL_RESOLUTION_SCOPE`
- `PCG_VARIABLE_SCOPE`
- `PCG_INDEX_QUEUE_DEPTH`
- `PCG_REPO_FILE_PARSE_MULTIPROCESS`
- `PCG_MULTIPROCESS_START_METHOD`

These are silently ignored by the Go binaries. Wiring must be split between
env vars whose consuming workload is actually rendered today vs. env vars
that belong to workloads not yet in the chart (bootstrap-index,
workflow-coordinator).

**Wire NOW — consumers render today:**

- Ingester (StatefulSet):
  - `PCG_PARSE_WORKERS`
  - `PCG_SNAPSHOT_WORKERS`
  - `PCG_LARGE_REPO_FILE_THRESHOLD`
  - `PCG_LARGE_REPO_MAX_CONCURRENT`
- Reducer / resolution-engine (Deployment):
  - `PCG_REDUCER_WORKERS`
  - `PCG_SHARED_PROJECTION_WORKERS`
  - `PCG_SHARED_PROJECTION_PARTITION_COUNT`
  - `PCG_SHARED_PROJECTION_BATCH_LIMIT`
  - `PCG_SHARED_PROJECTION_POLL_INTERVAL`
  - `PCG_SHARED_PROJECTION_LEASE_TTL`
  - `PCG_REDUCER_BATCH_CLAIM_SIZE`
- All Go workloads (optional, node-dependent):
  - `GOMEMLIMIT`

**Reserve — do NOT wire into chart until consumer lands:**

- `PCG_PROJECTION_WORKERS` — bootstrap-index. Per D2.7, bootstrap-index has
  no Kubernetes rendering path today. Adding this env var to the chart
  now would only attach to a workload that does not exist; defer until a
  bootstrap-index Job or init container is decided.
- Workflow-coordinator tuning (`PCG_WORKFLOW_COORDINATOR_*`) — covered by
  D2.1/D2.2 when the coordinator Deployment/values block lands.

#### D2.5 MCP-server deployment gap (pre-existing in both charts)

Neither upstream nor IaC chart ships a separate Deployment for
`pcg-mcp-server`. The ops-qa gateway exposes `mcp-pcg.qa.ops.bgrp.io`, but
the backing service routes to `pcg-api` which runs only `pcg-api` (HTTP API,
`/api/*`). The API binary does not mount the MCP SSE or `/mcp/message`
transport — that is the MCP-server binary’s job per
`docs/docs/deployment/service-runtimes.md` §MCP Server.

Two acceptable remediations (pick one before merge):

- **Option A (preferred):** add `deployment-mcp-server.yaml` and
  `service-mcp-server.yaml` to upstream `deploy/helm/platform-context-graph/`
  and mirror them into the IaC chart. Update the ops-qa HTTPRoute/Gateway
  parent ref to point at the new MCP service.
- **Option B:** retire or rename the `mcp-pcg.qa.ops.bgrp.io` hostname
  entirely (e.g., to `api-pcg.qa.ops.bgrp.io`). Do NOT keep an MCP-branded
  hostname routing to the API service while documenting that MCP is absent —
  that is a contract lie that will mislead operators and IDE clients. If
  MCP transport is deferred, the overlay must not advertise an MCP
  hostname at all until the MCP Deployment lands.

Either way, the current config is misleading and must be resolved before
merge to avoid landing a public endpoint whose DNS advertises a protocol
it does not serve.

#### D2.6 Image tag

- IaC `chart/Chart.yaml appVersion: "v0.0.58"` and `chart/values.yaml
  image.tag: "v0.0.58"` predate this branch HEAD. The CI image pipeline for
  `boatsgroup.pe.jfrog.io/bg-docker/platformcontextgraph` must build and push
  a new tag from this branch before the ops-qa argocd sync will find the
  image.
- Tag proposal: `v0.1.0-go` or a date-stamped tag like `v0.1.0-20260420`,
  reflecting the Python→Go cutover.

#### D2.7 ArgoCD sync ordering + schema bootstrap gap

**Schema bootstrap is currently absent from both charts.** Correction to
earlier draft wording: neither the IaC chart
(`~/repos/mobius/iac-eks-pcg/chart/templates/statefulset.yaml:50`) nor the
upstream chart (`deploy/helm/platform-context-graph/templates/`) ships a
`pcg-bootstrap-data-plane` init container. The only init container in
either chart is the ingester `workspace-setup` step
(`chart/templates/statefulset.yaml:51`). That step only prepares the PVC
directory; it does NOT run DDL against Postgres or Neo4j.

Consequences:

- On a cold environment, the API/ingester/reducer pods will start against
  empty databases. DDL must be applied by some other mechanism (manual
  `psql`, an out-of-band migration Job, or the runtime's lazy schema apply
  on first write). Merging without clarifying this will produce a broken
  first-sync in ops-qa.
- The `docs/docs/deployment/service-runtimes.md` and CLAUDE.md references
  to `pcg-bootstrap-data-plane` describe a runtime that exists as a
  binary/compose service but has no Kubernetes rendering path in either
  chart today.

Required before merge:

1. Decide whether schema bootstrap is (a) deliberately absent because the
   Go runtimes apply DDL on startup, (b) implicit via `pcg-bootstrap-index`
   as a one-shot Job, or (c) missing and must be added as a
   `pcg-bootstrap-data-plane` Kubernetes `Job` or init container.
2. Document the chosen answer in `service-runtimes.md` and carry it into
   the chart.

ArgoCD wave guidance (independent of the schema question):

- `argocd.syncWave: "1"` at both base and overlay is acceptable for the
  application chart once the schema question above is resolved.
- Verify neo4j + postgresql Helm releases sit in an earlier wave (or use
  `dependsOn`) so application pods can reach the databases on first sync.
  Base kustomization already includes `externalsecret-*` resources;
  confirm they finish reconciling before application manifests apply.

### D3 — Acceptance Criteria For Merge

This ADR is accepted and the branch may merge to `main` only after:

- [ ] D1 local MCP self-indexing validation run; result captured in merge PR body.
- [ ] D2.1 IaC chart PR adds `deployment-workflow-coordinator.yaml`,
      `service-workflow-coordinator.yaml`, and `networkpolicy.yaml`.
- [ ] D2.2 IaC `values.yaml` adds `workflowCoordinator:`, per-service
      `connectionTuning:`, and `networkPolicy:` blocks with safe defaults
      (dark, disabled, empty). Do NOT re-add `observability:` or
      `initContainerSecurityContext` — both already present.
- [ ] D2.3 IaC `_helpers.tpl` carries the required helper functions.
- [ ] D2.4 IaC `values.yaml` and ops-qa overlay python-era env-var keys
      removed; Go-runtime tuning env vars wired where needed.
- [ ] D2.4 (blast radius) IaC chart tests updated:
      `chart/tests/runtime-api-ingester-split.sh:105` asserts
      `PCG_COMMIT_WORKERS` renders exactly once and will fail after the
      env-var cleanup. Replace with an assertion on the Go-runtime
      equivalent for a workload that actually renders today (e.g.
      `PCG_PARSE_WORKERS`, `PCG_SNAPSHOT_WORKERS`, or a reducer/shared
      projection tuning key). Do NOT switch this assertion to
      `PCG_PROJECTION_WORKERS`, because D2.4/D2.7 reserve that knob until a
      bootstrap-index Kubernetes workload exists.
      Audit other chart test files for additional python-era env-var
      assertions.
- [ ] D2.4 (doc drift) IaC `README.md:11` ("MCP/API surface"),
      `AGENTS.md:23–30` ("HTTP API + MCP", "pcg serve start" runtime
      command), and upstream `deploy/helm/platform-context-graph/README.md:6`
      ("HTTP API + MCP") rewritten to match the split API + MCP Deployment
      contract from `docs/docs/deployment/service-runtimes.md`. Runtime
      command strings updated to `pcg api start` (or the chosen canonical
      command) where the docs mention the API boot path.
- [ ] D2.5 MCP-server deployment gap resolved under Option A (add MCP
      Deployment) or Option B (retire/rename the `mcp-pcg.*` hostname). Do
      NOT pick a hybrid that keeps an MCP-named hostname pointed at the
      API service.
- [ ] D2.6 A new image tag built from this branch HEAD is pushed to JFrog.
- [ ] D2.7 Schema bootstrap question answered (runtime applies DDL / Job /
      init container) and chart updated accordingly; `service-runtimes.md`
      reflects reality.
- [ ] `helm lint chart/` and `helm template chart/ -f argocd/.../ops-qa/app-values.yaml`
      both pass in the IaC repo.

---

## Consequences

### Positive

- Merging without D1 risks shipping an MCP-first product with no working MCP
  demonstration against its own codebase. The self-indexing loop is the
  fastest way to prove PCG/CGC lineage and the cheapest token-savings pitch.
- Merging without D2 risks deploying the ops-qa overlay with silently-broken
  env vars and no coordinator workload, forcing an emergency rollback and
  manual cluster cleanup.
- Documenting the python-era env-var drift here prevents operators from
  "tuning" symbols that have no effect in the Go runtime.

### Negative

- D2 adds scope to the branch beyond the Go data-plane slice. Accept the
  scope here because the chart parity is load-bearing for the first ops-qa
  deploy; deferring it means the branch merges but cannot be deployed.
- D2.5 may force a chart-template decision on MCP hosting that hasn’t
  surfaced before. Option B is still a real scope increase because it
  requires DNS/overlay cleanup and operator-doc rewrites even if the MCP
  Deployment itself is deferred.

### Risks

- If docker compose cannot index this repo (memory pressure, very large
  facts set), D1 becomes a task of its own. Start with `PCG_PARSE_WORKERS=2`
  and `PCG_LARGE_REPO_MAX_CONCURRENT=1` on macOS Docker Desktop.
- If the boats image pipeline lives outside this repo, D2.6 requires
  coordination with whoever owns the pipeline; surface that dependency early.

---

## Out Of Scope

- AWS cloud collector deployment shape (covered by the separate AWS collector
  ADR and its plan).
- Terraform-state collector deployment shape (covered by the tfstate ADR).
- Replacing `argocd.syncWave` with a richer dependency graph — current wave
  is acceptable.
- Neo4j or Postgres sizing changes for ops-qa.

---

## Open Questions

- Should the MCP deployment carry its own `ServiceMonitor`, or reuse the
  API’s? Upstream `servicemonitor.yaml` covers API + ingester + reducer +
  coordinator; MCP was never added.
- Should `pcg-bootstrap-index` continue to be Docker-Compose-only, or does
  the ops-qa environment want a one-shot `Job` manifest for empty-environment
  recovery? D2.7 keeps this open on purpose: if bootstrap schema/state cannot
  be guaranteed by the hosted runtimes, a Kubernetes Job may be the cleanest
  answer. Resolve this together with the schema-bootstrap decision rather than
  assuming compose-only up front.
