# Relationships Package

This package owns evidence-backed repository relationship discovery, resolution, persistence, and projection.

The current design is:

1. build checkout identities for the committed repos
2. collect graph-derived and raw file-based evidence
3. resolve evidence plus assertions into canonical relationships
4. persist a generation in Postgres
5. project the active resolved generation into Neo4j

## Module Map

| Module | Responsibility |
| :--- | :--- |
| `models.py` | Dataclasses for checkouts, evidence, candidates, assertions, resolved relationships, and generations |
| `identity.py` | Stable checkout identity helpers |
| `file_evidence.py` | Raw file-based extractors for Terraform, Helm, Kustomize, and ArgoCD ApplicationSets |
| `execution.py` | Checkout discovery, graph-derived evidence, and Neo4j projection |
| `resolver.py` | Evidence dedupe, candidate building, assertion application, suppression rules, and end-to-end resolution orchestration |
| `postgres.py` | Read and write APIs for assertions, candidates, generations, and resolved relationships |
| `postgres_generation.py` | Bulk generation persistence helpers |
| `postgres_support.py` | Postgres schema bootstrap for relationship tables |
| `state.py` | Shared relationship store lifecycle |

## Design Rules

### Postgres is canonical

Postgres stores:

- evidence facts
- candidates
- assertions and rejections
- resolved generations

Neo4j is the projected read model used by the existing query surfaces.

### Resolution is post-index

Relationship resolution is a post-index step. We do not try to correlate repos while a repo is only partially indexed.

### Preserve semantics

Do not flatten every mapping to `DEPENDS_ON`.

Current types:

- `DEPENDS_ON`
- `DISCOVERS_CONFIG_IN`
- `DEPLOYS_FROM`
- `PROVISIONS_DEPENDENCY_FOR`

Preferred future vocabulary:

- `PROVISIONS_PLATFORM`
- `RUNS_ON`

If a typed relationship exists for the same implied dependency pair, the resolver suppresses the generic inferred `DEPENDS_ON` candidate for that pair.
After typed resolution, the resolver derives a compatibility `DEPENDS_ON` edge in the dependency direction implied by the typed relationship unless that generic edge was explicitly rejected.

`DEPLOYS_FROM` is now implemented for deployable repos and config subjects when the evidence clearly identifies the repo that supplies manifests, charts, overlays, or release artifacts. The same semantic should be reused for future FluxCD and GitHub Actions mappings when the deployed repo or workflow subject clearly sources deployment artifacts from another repo.

`PROVISIONS_DEPENDENCY_FOR` is now implemented for Terraform/Terragrunt repo mappings where the infra repo clearly provisions resources or deploy-config dependencies for an application repo without being the service deployer itself.

## Where To Add New Mappings

### Raw file mappings

If the source of truth is checked-in config, add a focused extractor to `file_evidence.py` and call it from `discover_checkout_file_evidence(...)`.

Use this path for things like:

- Terraform or Terragrunt configuration
- Helm chart metadata and values
- Kustomize resources and image references
- ArgoCD ApplicationSets
- future GitHub Actions or FluxCD config files

For future deploy-control mappings, do not stop at a generic extractor that emits only `DEPENDS_ON` if the evidence clearly distinguishes config discovery from deployment source selection.

### Graph-derived mappings

If the signal already exists in the graph and is trustworthy, extend `discover_repository_dependency_evidence(...)` in `execution.py`.

### Resolver behavior

If a new typed relationship needs precedence or conflict rules, change `resolver.py` and add tests that prove the intended suppression or coexistence behavior.

### CLI review flows

If users need to inspect or override the new mapping from the CLI, update `cli/commands/ecosystem_relationships.py`.

## Checklist For A New Mapping

1. Pick the right relationship type before writing extraction code.
2. Emit a stable `evidence_kind`.
3. Include explainable `details` with path, matched value, extractor name, and tool context.
4. Add OTEL spans around the extractor or evidence source.
5. Emit JSON logs with stable `event_name` values and mapping counts under `extra_keys`.
6. Add positive and negative tests.
7. Validate the mapping on a mixed local corpus, not just a synthetic one-repo fixture.
8. Decide explicitly whether the new mapping should emit `DISCOVERS_CONFIG_IN`, `DEPLOYS_FROM`, or a generic fallback.

## Choosing The Next Type

Use this quick rule of thumb when we add support for more tools:

- choose `DISCOVERS_CONFIG_IN` when the source watches or scans another repo for config
- choose `DEPLOYS_FROM` when the source repo or deployable subject is deployed from artifacts, manifests, charts, or overlays owned by another repo
- choose `PROVISIONS_PLATFORM` when the source creates the runtime platform itself
- choose `RUNS_ON` when the source workload runs on that platform
- choose `PROVISIONS_DEPENDENCY_FOR` when the source creates infra the target needs but does not deploy the target
- choose `DEPENDS_ON` only when none of the above is precise enough yet

## Platform Modeling In This Slice

The Postgres relationship resolver is still repo-to-repo. For this slice, generic `Platform` nodes and `RUNS_ON` / `PROVISIONS_PLATFORM` edges are materialized on the graph/workload side in `tools/graph_builder_workloads.py`.

That means:

- repo-to-repo canonical truth still lives in the relationship tables
- `Platform` stays graph-internal for now
- ECS and EKS runtime/platform semantics are visible in Neo4j without widening the Postgres relationship schema yet

## Observability Requirements

Relationship code uses the shared observability subsystem under `observability/`.

Rules:

- stdout JSON is the canonical log format
- keep custom dimensions under `extra_keys`
- use stable machine-readable `event_name` values
- start OTEL spans around extractor families and the overall resolve/projection stages
- keep trace and log correlation fields intact with `run_id`, `generation_id`, and `scope`

Useful existing events:

- `relationships.discover_file_evidence.completed`
- `relationships.discover_evidence.completed`
- `relationships.persist_generation.completed`
- `relationships.project.completed`
- `relationships.resolve.completed`
- `relationships.resolve.failed`

Useful existing span names:

- `pcg.relationships.discover_evidence`
- `pcg.relationships.discover_evidence.file`
- `pcg.relationships.discover_evidence.terraform`
- `pcg.relationships.discover_evidence.helm`
- `pcg.relationships.discover_evidence.kustomize`
- `pcg.relationships.resolve_repository_dependencies`
- `pcg.relationships.project`

## Current Example

ArgoCD repo discovery is modeled as:

```text
iac-eks-argocd -[:DISCOVERS_CONFIG_IN]-> iac-eks-observability
api-node-bw-home -[:DEPLOYS_FROM]-> helm-charts
```

Those edges mean the ArgoCD repo discovers deployment config in the target repo, while the deployed service sources manifests or charts from another repo. They are intentionally not flattened into a generic `DEPENDS_ON`.
