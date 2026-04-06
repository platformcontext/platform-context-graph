# Service Story Follow-Ups

Date: 2026-04-05

## Goal

Close the remaining gaps surfaced by the `api-node-boats` support-document
investigation after the Phase A fixes for repository identity, search
ergonomics, deployment-story pruning, and service-story GitOps promotion.

## What Landed Already

- Repository IDs now preserve the stored graph identifier across public refs.
- Content search treats `artifact_types=["file"]` as matching ordinary source
  rows that do not carry an explicit artifact type.
- Content search resolves fuzzy repository filters like `helm-charts` to the
  canonical repository identifier before querying Postgres.
- Service/workload stories can inherit GitOps evidence from repository fallback
  matches even when the workload graph is incomplete.
- Consumer repositories no longer pollute support dependency hotspots.
- Low-signal Terraform fan-out no longer becomes the main deployment story.
- Config-only environments such as `bg-qa` can backfill service selection when
  a runtime instance row is missing.
- Workload/service stories now expose stronger deployment sections and rank
  public environment-matching entrypoints ahead of lower-signal paths.

## Remaining Gaps

### 1. Key Artifact Ranking

Support answers still need more deterministic promotion of the artifacts that
operators reach for first.

Priority artifacts:

- environment overlay values files
- base values files
- probe and health endpoint definitions
- runtime bootstrap or main service entrypoint files
- IRSA, secret, or config-access manifests
- dashboards and service-monitoring assets
- OpenAPI or route-specification files

Implementation target:

- add a dedicated artifact-ranking helper that blends graph context, GitOps
  context, and Postgres-backed documentation evidence
- keep artifact ranking explicit and explainable instead of burying it inside
  generic documentation selection

### 2. Service Story and Deployment Trace Convergence

The service story is much stronger now, but the best GitOps evidence still
shows up more completely in `trace_deployment_chain(...)` than in
`get_service_story(...)`.

Implementation target:

- unify the shaping rules for:
  - ArgoCD owner
  - values layers
  - rendered resources
  - supporting Kustomize resources
- make sure service stories consume the same pruned, support-friendly
  deployment evidence as the trace handler

### 3. Deployment-Chain Pruning

The worst Terraform fallback noise is fixed, but wide traces can still surface
more side-context than a support engineer needs.

Implementation target:

- keep default story shaping focused on:
  - direct GitOps controllers
  - deployment repos
  - service-specific rendered resources
  - service-specific support artifacts
- relegate broad Terraform or provisioning context to drill-downs or explicit
  deep-trace modes

### 4. Environment Normalization

`bg-qa` config-only environments work better now, but environment naming still
deserves a more global normalization pass.

Implementation target:

- normalize environment comparison across:
  - workload instances
  - hostname/config evidence
  - GitOps overlays
  - namespace-derived fallbacks
- validate additional naming shapes such as:
  - `qa`
  - `ops-qa`
  - `prod-us`
  - namespace-only environment hints

### 5. Support-Oriented Content Selection

Postgres content is available, but support stories still need stronger
targeting when deciding which indexed docs and files matter most.

Implementation target:

- distinguish:
  - operator-facing docs
  - deployment/config files
  - application runtime files
  - observability assets
- use that classification to improve support summaries and first-15-minute
  investigation guidance

## Recommended Order

1. Implement deterministic key-artifact ranking.
2. Reuse the same ranked artifact set in support overview generation.
3. Continue pruning deployment-chain evidence before it reaches service-story
   shaping.
4. Broaden environment normalization coverage.
5. Revisit content-search ranking only after the orchestration changes settle.

## Acceptance Criteria For The Next Slice

- A support-style story for `api-node-boats` promotes overlay values, probe or
  health artifacts, runtime bootstrap files, and dashboards without manual
  drill-downs.
- `get_service_story(...)` and `trace_deployment_chain(...)` agree on the
  primary GitOps owner and top deployment artifacts.
- Consumer repositories remain visible, but never appear as runtime dependency
  hotspots.
- Config-only environments continue to resolve cleanly for support stories.
- Focused story and context regressions stay green.

## Post-PR-76 Backlog

The evidence-based deployment contract is now in place. The next work should
focus on improving the evidence that feeds that contract instead of adding more
story-only shaping.

### Priority 1. Artifact Ranking And Support Selection

Goal:

- make support-oriented stories consistently promote the first files an
  operator should open

Remaining work:

- add a deterministic artifact-ranking helper
- score GitOps overlays, values, probes, bootstrap files, IRSA/secret/config
  manifests, dashboards, and API specs explicitly
- reuse the same ranked artifact set in:
  - `get_service_story(...)`
  - `get_repo_story(...)`
  - `trace_deployment_chain(...)`
  - support overview shaping

Acceptance criteria:

- top artifacts are stable across story surfaces for the same service
- overlay values, probes, bootstrap files, and dashboards appear before lower
  signal docs

### Priority 2. Deployment Trace Convergence And Pruning

Goal:

- keep service stories and deployment traces aligned on the same primary
  deployment evidence

Remaining work:

- reuse the same deployment-owner and artifact-selection logic across story and
  trace handlers
- prune broad provisioning fan-out from default support answers
- keep deep infra context available only in drill-down paths or explicit deep
  traces

Acceptance criteria:

- `get_service_story(...)` and `trace_deployment_chain(...)` agree on the
  primary owner and top deployment artifacts
- unrelated Terraform or provisioning estates do not dominate default support
  answers

### Priority 3. Environment Normalization

Goal:

- make environment selection behave consistently across runtime, config, and
  deployment evidence

Remaining work:

- normalize environment comparison across workload instances, hostnames,
  overlays, namespaces, and config-derived hints
- add regression coverage for:
  - `qa`
  - `bg-qa`
  - `ops-qa`
  - `prod-us`
  - namespace-only hints

Acceptance criteria:

- environment-aware service stories select the same environment from runtime
  and config-backed evidence
- config-only estates keep working without pretending a runtime instance exists

### Priority 4. Parser And Context Enrichment

Goal:

- improve the raw deployment evidence available to the mapper

Remaining work:

- broaden controller-free Helm and manifest detection
- strengthen CloudFormation-to-runtime linking
- strengthen ECS service and task linking
- continue expanding the synthetic fixture corpus for mixed deployment estates
- validate against real indexed services across:
  - ArgoCD
  - Flux
  - Terraform
  - CloudFormation/ECS or Lambda
  - controller-free local Helm/manifests

Acceptance criteria:

- parser/context layers produce richer `delivery_paths` and
  `controller_driven_paths` before story shaping runs
- live validation shows fewer `mapping_mode=none` cases caused by missing raw
  evidence

### Priority 5. Support-Oriented Content Classification

Goal:

- better distinguish what kind of file or doc an operator is looking at

Remaining work:

- classify content into:
  - operator docs
  - deployment/config files
  - runtime source files
  - observability assets
- use that classification to improve support summaries and first-15-minute
  investigation guidance

Acceptance criteria:

- support guidance favors operator and deployment artifacts ahead of generic
  repository docs
- observability assets are promoted when incident investigation is the likely
  user intent

## Recommended Order After PR #76

1. Finish deterministic artifact ranking and reuse it across all story
   surfaces.
2. Align deployment traces with service-story shaping and prune default
   fan-out.
3. Broaden environment normalization coverage.
4. Continue parser/context enrichment and mixed-estate validation.
5. Tighten support-oriented content classification once the richer evidence
   layer has settled.
