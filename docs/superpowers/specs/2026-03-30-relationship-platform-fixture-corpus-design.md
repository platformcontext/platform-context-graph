# Relationship Platform Fixture Corpus Design

**Goal:** define one environment-neutral, layered fixture corpus that proves the full relationship pipeline across Terraform, Terragrunt, Route53, CloudFront, Cloudflare, Helm, Kustomize, ArgoCD, Jenkins, GitHub Actions, ECS, EKS, workload finalization, and story/query surfaces.

## Scope

This corpus is for compose-backed local end-to-end validation. It is not meant to mirror production scale. It is meant to create a small but realistic multi-layer platform graph with explicit expected relationships.

Constraints:
- No real environment names.
- No customer, brand, or internal naming.
- One logical public service is dual deployed during migration.
- One worker service uses only the modern path.
- Assertions must validate individual relationship types, not just "the story looks good."

## Corpus Topology

The corpus contains ten synthetic repositories.

1. `service-edge-api`
2. `service-worker-jobs`
3. `deployment-helm`
4. `deployment-kustomize`
5. `delivery-argocd`
6. `delivery-legacy-automation`
7. `infra-network-foundation`
8. `infra-runtime-legacy`
9. `infra-runtime-modern`
10. `infra-modules-shared`

### Service Model

`service-edge-api` is one logical service with two active runtime paths:
- public legacy path through ECS
- internal migration path through EKS

`service-worker-jobs` is one internal worker with only the modern EKS path.

### Edge Model

The edge layer intentionally mixes providers:
- Route53
- CloudFront
- Cloudflare

The DNS model is:
- `api.example.test`
  - public legacy endpoint
  - Route53 and CloudFront
  - resolves to the ECS path
- `api-modern.internal.test`
  - internal migration endpoint
  - Cloudflare and optional Route53 support
  - resolves to the EKS path

## Expected Relationship Types

The fixture must explicitly assert these types:

- `PROVISIONS_DEPENDENCY_FOR`
- `PROVISIONS_PLATFORM`
- `RUNS_ON`
- `DEPLOYS_FROM`
- `DISCOVERS_CONFIG_IN`
- `DEPENDS_ON`
- `DEPLOYMENT_SOURCE`
- `DEFINES`
- `INSTANCE_OF`
- `WORKLOAD_DEPENDS_ON`

## Repository Responsibilities

### `service-edge-api`

Purpose:
- application repo for the dual-deployed edge service

Files:
- `Dockerfile`
- `src/app.py` or `src/server.js`
- `.github/workflows/deploy-legacy.yml`
- `Jenkinsfile`
- `config/runtime.yaml`

Signals to create:
- GitHub Actions deployment automation
- Jenkins deployment automation
- service/workload identity
- runtime dependency hints that can produce workload-level dependencies

Expected relationships:
- `DEFINES`
- `INSTANCE_OF`
- `RUNS_ON` to ECS and EKS
- `DEPLOYMENT_SOURCE` to legacy and modern deployment repos
- `WORKLOAD_DEPENDS_ON` to `service-worker-jobs`

### `service-worker-jobs`

Purpose:
- modern-only worker service

Files:
- `Dockerfile`
- `src/worker.py` or `src/worker.js`
- `.github/workflows/deploy-modern.yml`
- `config/runtime.yaml`

Signals to create:
- workload identity
- modern deployment automation

Expected relationships:
- `DEFINES`
- `INSTANCE_OF`
- `RUNS_ON` to EKS
- `DEPLOYMENT_SOURCE` to modern deployment repo

### `deployment-helm`

Purpose:
- Helm source of truth for both services

Files:
- `charts/edge-api/Chart.yaml`
- `charts/edge-api/values.yaml`
- `charts/edge-api/templates/deployment.yaml`
- `charts/edge-api/templates/service.yaml`
- `charts/worker-jobs/Chart.yaml`
- `charts/worker-jobs/values.yaml`
- `charts/worker-jobs/templates/deployment.yaml`

Signals to create:
- Helm chart references for both services

Expected relationships:
- `DEPLOYS_FROM` to `service-edge-api`
- `DEPLOYS_FROM` to `service-worker-jobs`

### `deployment-kustomize`

Purpose:
- modern deployment overlays

Files:
- `overlays/modern/kustomization.yaml`
- `overlays/modern/edge-api-values.yaml`
- `overlays/modern/worker-jobs-values.yaml`

Signals to create:
- Kustomize references to Helm charts
- modern deployment-source chain

Expected relationships:
- `DEPLOYS_FROM` to `deployment-helm`

### `delivery-argocd`

Purpose:
- ArgoCD delivery repo for the modern path

Files:
- `applications/edge-api.yaml`
- `applications/worker-jobs.yaml`
- `applicationsets/platform-apps.yaml`

Signals to create:
- Application deploy-source references
- ApplicationSet config discovery
- destination/runtime platform evidence

Expected relationships:
- `DEPLOYS_FROM` to `deployment-kustomize`
- `DISCOVERS_CONFIG_IN` to `deployment-kustomize`
- `RUNS_ON` platform evidence feeding modern runtime path

### `delivery-legacy-automation`

Purpose:
- legacy ECS delivery repo

Files:
- `pipelines/deploy-edge-api.groovy`
- `.github/workflows/promote-edge-api.yml`
- `scripts/register-task.sh`

Signals to create:
- Jenkins-driven legacy deploy signal
- optional GHA-driven legacy promotion signal

Expected relationships:
- `DEPLOYS_FROM` to `service-edge-api`

### `infra-network-foundation`

Purpose:
- network and edge infrastructure

Files:
- `main.tf`
- `edge.tf`
- `dns.tf`
- `cdn.tf`

Resources to include:
- VPC
- subnets
- security groups
- ALB or NLB
- Route53 records
- CloudFront distribution
- Cloudflare DNS record or proxied record

Signals to create:
- edge chain for public legacy endpoint
- edge chain for internal modern endpoint
- platform provisioning signal

Expected relationships:
- `PROVISIONS_PLATFORM` to legacy edge/runtime platform
- `PROVISIONS_PLATFORM` to modern edge/runtime platform
- `PROVISIONS_DEPENDENCY_FOR` to `service-edge-api` where appropriate

### `infra-runtime-legacy`

Purpose:
- legacy ECS runtime stack

Files:
- `main.tf`
- `ecs.tf`
- `service.tf`
- `dns-bindings.tf`

Resources to include:
- ECS cluster
- task definition
- ECS service
- target group or listener attachment
- app-facing queue, registry, or config resources
- module reference to `infra-modules-shared`

Signals to create:
- legacy runtime platform provisioning
- legacy app dependency provisioning

Expected relationships:
- `PROVISIONS_PLATFORM` to ECS platform
- `PROVISIONS_DEPENDENCY_FOR` to `service-edge-api`
- `DEPENDS_ON` to `infra-modules-shared`

### `infra-runtime-modern`

Purpose:
- modern EKS runtime stack

Files:
- `terragrunt.hcl`
- `main.tf`
- `eks.tf`
- `ingress.tf`
- `services.tf`

Resources to include:
- EKS-facing runtime resources
- ingress or LB wiring
- app-facing resources for edge API and worker
- module reference to `infra-modules-shared`

Signals to create:
- modern runtime platform provisioning
- modern dependency provisioning
- Terragrunt to Terraform environment lineage

Expected relationships:
- `PROVISIONS_PLATFORM` to EKS platform
- `PROVISIONS_DEPENDENCY_FOR` to `service-edge-api`
- `PROVISIONS_DEPENDENCY_FOR` to `service-worker-jobs`
- `DEPENDS_ON` to `infra-modules-shared`

### `infra-modules-shared`

Purpose:
- shared Terraform modules used by both runtime repos

Files:
- `modules/runtime-service/main.tf`
- `modules/edge-routing/main.tf`
- `modules/shared-network/main.tf`

Signals to create:
- reusable module dependency targets

Expected relationships:
- incoming `DEPENDS_ON` from both runtime repos

## Target Chains

The corpus should support these query stories.

### Top-Down Infra Story

For `service-edge-api`, PCG should be able to reconstruct:

- public legacy path
  - Route53
  - CloudFront
  - load balancer
  - ECS runtime
  - service

- internal modern path
  - Cloudflare
  - Route53 or DNS record
  - ingress or load balancer
  - EKS runtime
  - service

### Bottom-Up Delivery Story

For `service-edge-api`, PCG should be able to reconstruct:

- legacy path
  - Jenkins or GitHub Actions
  - legacy deployment repo
  - ECS runtime

- modern path
  - ArgoCD
  - Kustomize
  - Helm
  - EKS runtime

### Terraform Lineage Story

PCG should be able to show:

- Terragrunt environment
- Terraform root
- shared Terraform module

for the modern path, and shared-module usage for the legacy path.

## Assertion Matrix

The first fixture version should assert at least these baseline edges.

- `PROVISIONS_DEPENDENCY_FOR`
  - `infra-runtime-legacy` -> `service-edge-api`
  - `infra-runtime-modern` -> `service-edge-api`
  - `infra-runtime-modern` -> `service-worker-jobs`

- `PROVISIONS_PLATFORM`
  - `infra-network-foundation` -> legacy platform
  - `infra-network-foundation` -> modern platform
  - `infra-runtime-legacy` -> ECS platform
  - `infra-runtime-modern` -> EKS platform

- `RUNS_ON`
  - `service-edge-api` -> ECS platform
  - `service-edge-api` -> EKS platform
  - `service-worker-jobs` -> EKS platform

- `DEPLOYS_FROM`
  - `delivery-argocd` -> `deployment-kustomize`
  - `deployment-kustomize` -> `deployment-helm`
  - `deployment-helm` -> `service-edge-api`
  - `deployment-helm` -> `service-worker-jobs`
  - `delivery-legacy-automation` -> `service-edge-api`

- `DISCOVERS_CONFIG_IN`
  - `delivery-argocd` -> `deployment-kustomize`

- `DEPENDS_ON`
  - `infra-runtime-legacy` -> `infra-modules-shared`
  - `infra-runtime-modern` -> `infra-modules-shared`

- `DEPLOYMENT_SOURCE`
  - legacy edge-api workload instance -> `delivery-legacy-automation`
  - modern edge-api workload instance -> `deployment-kustomize` or `deployment-helm`
  - worker workload instance -> `deployment-kustomize` or `deployment-helm`

- `DEFINES`
  - `service-edge-api` -> edge-api workload
  - `service-worker-jobs` -> worker workload

- `INSTANCE_OF`
  - edge-api legacy instance -> edge-api workload
  - edge-api modern instance -> edge-api workload
  - worker instance -> worker workload

- `WORKLOAD_DEPENDS_ON`
  - edge-api workload -> worker workload

## Fixture Directory Tree

The checked-in fixture corpus should live at:

`tests/fixtures/relationship_platform/`

Directory tree:

```text
tests/fixtures/relationship_platform/
  service-edge-api/
    Dockerfile
    Jenkinsfile
    config/runtime.yaml
    src/app.py
    .github/workflows/deploy-legacy.yml
  service-worker-jobs/
    Dockerfile
    config/runtime.yaml
    src/worker.py
    .github/workflows/deploy-modern.yml
  deployment-helm/
    charts/edge-api/Chart.yaml
    charts/edge-api/values.yaml
    charts/edge-api/templates/deployment.yaml
    charts/edge-api/templates/service.yaml
    charts/worker-jobs/Chart.yaml
    charts/worker-jobs/values.yaml
    charts/worker-jobs/templates/deployment.yaml
  deployment-kustomize/
    overlays/modern/kustomization.yaml
    overlays/modern/edge-api-values.yaml
    overlays/modern/worker-jobs-values.yaml
  delivery-argocd/
    applications/edge-api.yaml
    applications/worker-jobs.yaml
    applicationsets/platform-apps.yaml
  delivery-legacy-automation/
    pipelines/deploy-edge-api.groovy
    .github/workflows/promote-edge-api.yml
    scripts/register-task.sh
  infra-network-foundation/
    main.tf
    edge.tf
    dns.tf
    cdn.tf
  infra-runtime-legacy/
    main.tf
    ecs.tf
    service.tf
    dns-bindings.tf
  infra-runtime-modern/
    terragrunt.hcl
    main.tf
    eks.tf
    ingress.tf
    services.tf
  infra-modules-shared/
    modules/runtime-service/main.tf
    modules/edge-routing/main.tf
    modules/shared-network/main.tf
  expected_relationships.yaml
```

## Manifest Schema

The manifest should be one stable contract for the compose validator.

Path:
- `tests/fixtures/relationship_platform/expected_relationships.yaml`

Schema:

```yaml
corpus:
  name: relationship-platform
  description: >
    Synthetic dual-runtime platform migration corpus for relationship validation.

repositories:
  - name: service-edge-api
    role: service
  - name: service-worker-jobs
    role: service
  - name: deployment-helm
    role: deployment
  - name: deployment-kustomize
    role: deployment
  - name: delivery-argocd
    role: delivery
  - name: delivery-legacy-automation
    role: delivery
  - name: infra-network-foundation
    role: infrastructure
  - name: infra-runtime-legacy
    role: infrastructure
  - name: infra-runtime-modern
    role: infrastructure
  - name: infra-modules-shared
    role: module

expected_relationships:
  - relationship_type: PROVISIONS_DEPENDENCY_FOR
    source_repo: infra-runtime-legacy
    target_repo: service-edge-api
    min_count: 1
    rationale: Legacy ECS terraform provisions edge API resources.

  - relationship_type: RUNS_ON
    source_repo: service-edge-api
    target_entity:
      kind: Platform
      match:
        name_contains: ecs
    min_count: 1
    rationale: Edge API runs on legacy ECS runtime.

  - relationship_type: RUNS_ON
    source_repo: service-edge-api
    target_entity:
      kind: Platform
      match:
        name_contains: eks
    min_count: 1
    rationale: Edge API also runs on modern EKS runtime.

expected_story_checks:
  - repo: service-edge-api
    requires_runtime_platforms: 2
    requires_deployment_signal: true
    requires_dual_runtime_labels:
      - ecs
      - eks

expected_workloads:
  - repo: service-edge-api
    workload_name_contains: edge-api
    instance_count_at_least: 2
  - repo: service-worker-jobs
    workload_name_contains: worker
    instance_count_at_least: 1
```

Rules:
- `source_repo` and `target_repo` are for repo-to-repo edges.
- `target_entity` is for platform or workload edges when the target is not another repo.
- `min_count` defaults to `1`.
- `rationale` is required so failures are interpretable.

## Validation Strategy

The compose-backed validator should:

1. mount `tests/fixtures/relationship_platform/` as the filesystem root
2. run full indexing/finalization
3. load `expected_relationships.yaml`
4. assert every expected relationship by type
5. run story checks for `service-edge-api`
6. fail with a type-grouped report

Failure output should show:
- relationship type
- source
- target
- actual count
- expected count
- rationale

## Recommendation

Build this corpus in phases:

1. create the ten repos and baseline files
2. add the manifest with the baseline assertion set
3. wire a compose-backed validator
4. add story checks for dual runtime and delivery chain visibility

This keeps the fixture understandable while still covering the relationship types most likely to regress.
