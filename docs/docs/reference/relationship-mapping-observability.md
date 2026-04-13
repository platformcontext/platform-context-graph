# Relationship Mapping Observability

Use this page as the operational companion to
[Relationship Mapping](relationship-mapping.md).

The main relationship mapping reference explains stage ownership, typed
precedence, and extension rules. This companion focuses on the signals and
examples operators use when they need to prove that mapping behaved correctly.

## Logging

Relationship mapping uses the shared JSON logging contract.

Rules:

- keep stable machine-readable `event_name` values
- keep custom dimensions under `extra_keys`
- keep trace and correlation fields intact
- do not add ad hoc top-level log keys

Current relationship log families include:

- `relationships.discover_file_evidence.completed`
- `relationships.discover_gitops_evidence.completed`
- `relationships.discover_evidence.completed`
- `relationships.persist_generation.completed`
- `relationships.project.completed`
- `relationships.resolve.completed`
- `relationships.resolve.failed`

## OTEL Traces

Use OTEL spans around both the extractor family and the overall resolve/project
phases.

Current span families include:

- `pcg.relationships.discover_evidence`
- `pcg.relationships.discover_evidence.file`
- `pcg.relationships.discover_evidence.terraform`
- `pcg.relationships.discover_evidence.helm`
- `pcg.relationships.discover_evidence.kustomize`
- `pcg.relationships.discover_evidence.gitops`
- `pcg.relationships.discover_evidence.argocd`
- `pcg.relationships.resolve_repository_dependencies`
- `pcg.relationships.project`

## Required Tests

Every new mapping family should come with:

- unit tests for the extractor
- unit tests for resolver precedence or coexistence
- a negative test that proves unrelated repos stay unrelated
- a mixed-corpus validation run when the family changes answer shape

For this slice, the important relationship tests are in:

- `tests/unit/relationships/test_file_evidence.py`
- `tests/unit/relationships/test_resolver.py`

## Example Multi-Chain

One useful pattern from the local corpus is:

```text
gitops-control-plane
  DISCOVERS_CONFIG_IN -> platform-observability
  DISCOVERS_CONFIG_IN -> helm-charts

home-service
  DEPLOYS_FROM -> helm-charts

search-api
  DEPLOYS_FROM -> helm-charts

payments-api
  DEPLOYS_FROM -> helm-charts
```

That is more truthful than flattening everything into a generic dependency
chain. It preserves the control-plane meaning of the ArgoCD repository while
keeping downstream deployment answers queryable.
