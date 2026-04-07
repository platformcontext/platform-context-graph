# PCG Investigation Orchestration Design

## Summary

Platform Context Graph already has strong low-level investigation primitives:

- canonical entity resolution
- repository and workload stories
- deployment traces
- graph relationship analysis
- indexed file and entity content search

What it does not yet have is a strong, user-safe investigation layer that can
turn a normal support question into the right sequence of PCG calls.

Today, a user can ask a reasonable question like:

- "Explain the deployment flow for `api-node-boats` using PCG only."

and still get an incomplete answer unless the caller knows to manually widen
into adjacent deployment repositories like:

- GitOps repos
- ArgoCD repos
- Terraform stacks
- config or routing repos

This design adds that missing orchestration layer.

The goal is not to make users better prompt engineers. The goal is to make PCG
better at investigation.

## Problem

The current product has three related gaps.

### 1. Retrieval breadth is too manual

The strongest deployment or runtime evidence often lives outside the main app
repository. A user asking about a service typically expects PCG to widen into:

- app repo
- GitOps or deployment repo
- controller repo
- infrastructure repo
- runtime or routing repo

Today, that widening is inconsistent and often requires manual follow-up calls.

### 2. Strong evidence is not promoted early enough

Useful file-level evidence can already exist in indexed content, but the story
surface may not elevate it into the first answer. This creates a false
impression that PCG lacks the data, when the real problem is orchestration.

### 3. The system does not explain its own coverage

When an answer is incomplete, the user cannot easily tell whether:

- PCG did not search the right repos
- PCG searched them but the graph/content is partial
- PCG found relevant evidence but did not promote it

This makes the tool hard to trust for operators who are not prompt experts.

## Product Principle

Investigation is an orchestration problem.

PCG should not require the user to know:

- which repo family to search next
- which evidence family matters for the question
- which MCP call to run after the current one

Instead, PCG should:

1. classify the investigation intent
2. widen into the right evidence families
3. report what it searched
4. report what it found
5. report what is still missing
6. recommend or perform the next best drill-down

## User Experience Goal

A normal operator prompt should be enough.

Example:

- "Explain the deployment and network flow for `api-node-boats` using PCG only."

PCG should be able to return a materially complete answer without the user
having to specify:

- "also check the ArgoCD repo"
- "also check Terraform stacks"
- "also search GitHub Actions IAM roles"
- "also look for config overlays"

## Proposed Solution

Add a first-class investigation layer while preserving existing story tools.

### Public contract direction

Keep the existing tools:

- `get_repo_story`
- `get_workload_story`
- `get_service_story`
- `trace_deployment_chain`

Add a new top-level orchestration tool:

- `investigate_service`

Future siblings may include:

- `investigate_repository`
- `investigate_deployment`
- `investigate_runtime`

V1 only requires `investigate_service`.

## Why A New Tool

Improving existing story tools is necessary but not sufficient.

If the system only becomes "more magical" inside existing tools:

- coverage is harder to explain
- missing evidence is harder to diagnose
- evaluation is harder to standardize
- users still do not know when the answer is partial

The investigation tool solves that by making orchestration explicit.

## V1 Tool Contract

### `investigate_service`

Purpose:

- answer a support, architecture, deployment, runtime, or dependency question
  about a service using coordinated PCG evidence retrieval

Inputs:

- `service_name`
- optional `environment`
- optional `intent`

Recommended intent families:

- `deployment`
- `network`
- `dependencies`
- `support`
- `overview`

If `intent` is omitted, V1 should infer it from the question or default to
`overview`.

Outputs:

- concise `summary`
- `repositories_considered`
- `repositories_with_evidence`
- `evidence_families_found`
- `coverage_summary`
- `investigation_findings`
- `limitations`
- `recommended_next_steps`
- `recommended_next_calls`

This response should be additive and structured enough for:

- MCP use
- HTTP use
- prompt-driven synthesis
- future UI rendering

## Investigation Model

### Step 1. Resolve the subject

Start with canonical identity resolution for:

- service workload
- primary repository
- known aliases

### Step 2. Classify intent

Decide what kind of question the user is asking.

Examples:

- deployment question
- network question
- dependency question
- support question

The intent controls which evidence families are widened first.

### Step 3. Expand into evidence families

For service investigation, V1 should search across these families.

#### Service/runtime family

- app repo
- runtime config files
- Dockerfile or runtime packaging
- entrypoints
- ports
- public/internal hostnames

#### Deployment/controller family

- ArgoCD
- Flux
- controller-driven deployment repositories
- Helm or Kustomize overlays

#### Infrastructure/IaC family

- Terraform stacks
- CloudFormation repos
- ECS or Kubernetes infrastructure repos
- IAM or CI/CD role definitions

#### Network/routing family

- DNS names
- gateway hosts
- target groups
- ingress or route config
- service discovery or namespace hints

#### Dependency family

- downstream service/client usage
- upstream consumers
- caches
- data stores
- support systems

#### Documentation/support family

- operator docs
- runbooks
- monitoring assets
- API specs
- health and readiness definitions

### Step 4. Detect multi-plane deployment

If multiple deployment evidence families are found, the response must not
collapse them.

Examples:

- ArgoCD plus Terraform
- Kubernetes plus ECS
- GitOps plus infrastructure stack

When this happens, the response must surface:

- `deployment_planes`
- the evidence for each plane
- how the planes relate

### Step 5. Report coverage

Every investigation result should say what it searched and what it did not
prove.

V1 coverage reporting should include:

- repo families searched
- repo families found
- evidence families searched
- evidence families found
- graph completeness caveats
- content completeness caveats
- whether the answer is single-plane, multi-plane, or sparse

## Evidence Families

V1 uses explicit evidence-family reporting.

Proposed families:

- `service_runtime`
- `deployment_controller`
- `gitops_config`
- `iac_infrastructure`
- `network_routing`
- `identity_and_iam`
- `dependencies`
- `support_artifacts`
- `monitoring_observability`
- `ci_cd_pipeline`

These families serve two purposes:

1. improve the answer
2. expose what has and has not been searched well enough

## Related Repository Widening Rules

V1 should widen automatically using factual evidence, not naming guesswork
alone.

Signals that justify widening:

- repo references embedded in ApplicationSets or deployment specs
- overlay paths or values sources
- Terraform role subjects or GitHub OIDC bindings
- shared image names or image repositories
- shared config paths like SSM parameter prefixes
- direct service-name references in deployment files
- controller trace outputs that mention external source repositories

Repo-name heuristics are allowed only as a secondary signal.

Examples:

- `helm-*`
- `iac-*`
- `terraform-*`
- `argocd-*`

## Recommended Next Calls

The system should not only answer. It should guide the next drill-down.

Every investigation result should be able to return:

- likely next repos
- likely next tools
- why each next step is recommended

Example:

- `get_repo_story(terraform-stack-node10)` because GitHub OIDC and ECS target
  group evidence was found there
- `search_file_content("api-node-boats", repo_id=terraform-stack-node10)`
  because the story is graph-partial but file content exists

## Existing Tool Improvements

Even with a new orchestrator, existing story tools should improve.

### `get_service_story`

Should gain:

- related deployment repos
- evidence-family summary
- multi-plane hints
- stronger limitations when evidence is sparse

### `trace_deployment_chain`

Should gain:

- better repo widening hints
- better distinction between direct deployment evidence and broad infra fan-out
- stronger integration with multi-plane reporting

## Truthfulness Rules

The investigation layer must never hide uncertainty.

- Do not claim a deployment plane unless a supporting evidence family exists.
- Do not say a repo is irrelevant just because it was not surfaced by the first
  story call.
- Do not present partial search as complete coverage.
- Distinguish:
  - not searched
  - searched but no evidence found
  - evidence found but graph/story incomplete

## Evaluation Standard

The product should be judged using short, natural prompts.

Good evaluation prompts:

- "Explain the deployment flow for `api-node-boats` using PCG only."
- "What depends on `api-node-boats` and what does it depend on?"
- "Explain the network flow for `api-node-boats` using PCG only."

Bad evaluation methodology:

- requiring long rescue prompts that enumerate every repo family manually

If a normal support prompt cannot recover deployment-adjacent repos and
multiple evidence planes, the product is not yet strong enough.

## Acceptance Criteria

### V1 investigation quality

For a service like `api-node-boats`, a normal investigation prompt should
surface:

- the app repo
- GitOps repo
- controller repo
- relevant Terraform or infrastructure repo
- major hostnames, ports, and health endpoints
- upstream consumers
- downstream dependencies
- strong evidence versus missing evidence

### V1 coverage reporting

The investigation result must make it clear whether:

- relevant infra repos were searched
- multiple deployment planes were detected
- graph/content incompleteness is limiting the answer

### V1 operator trust

A user should be able to tell:

- why a repo was included
- why a repo was not included
- what to query next if more detail is needed

## Out Of Scope For V1

- full auto-generated runbooks
- persona-specific answer template engines
- a generalized orchestration tool for every entity type
- replacing all current story endpoints
- solving every parser/indexing gap before the investigation layer ships

## Implementation Direction

The implementation should happen in this order:

1. write the orchestration PRD and acceptance tests
2. add investigation response models
3. implement repo/evidence-family widening helpers
4. implement multi-plane detection
5. add coverage and recommended-next-call reporting
6. integrate lightweight hints into existing story surfaces
7. validate against real services, including `api-node-boats`

## Success Metric

Success is not "the model can answer if the prompt is clever enough."

Success is:

- a normal prompt gets a broad, evidence-backed answer
- the answer explains what it searched
- the user can see what is still missing
- PCG feels investigatory, not fragile
