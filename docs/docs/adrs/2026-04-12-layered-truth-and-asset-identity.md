# ADR: Layered Truth And Asset Identity

**Status:** Accepted

## Context

PCG needs to correlate code, IaC, applied state, and live infrastructure
without collapsing those layers into one ambiguous node type. Operators want to
know not only what resource exists, but whether it is declared in source,
applied in state, observed in the provider, or canonically resolved across all
three.

Without a locked truth model, future collectors will create inconsistent
identity rules and the graph will become harder to trust as AWS, Kubernetes,
Terraform state, CloudFormation state, and future infrastructure sources land.

## Decision

PCG will use a four-layer truth model for infrastructure and platform assets:

1. `SourceDeclaration`
2. `AppliedDeclaration`
3. `ObservedResource`
4. `CloudAsset`

`CloudAsset` is the canonical resolved asset. The other three layers preserve
their own provenance, timestamps, and source-system semantics.

Identity rules are:

- use provider-native identifiers first when they are stable
- preserve the original source-local identifier alongside the canonical one
- keep the layer that produced a record queryable
- attach evidence to the canonical asset instead of erasing the source record

Examples:

- AWS resources should anchor on ARN when ARN exists
- Azure resources should anchor on Azure resource ID
- GCP resources should anchor on provider resource name or self link
- Kubernetes resources should anchor on stable cluster and object identity,
  using UID only where it remains useful for reconciliation rather than as the
  only portable key

## Why This Choice

- It lets PCG answer "declared but not applied" without guessing.
- It lets PCG answer "observed but not IaC-managed" as a first-class case.
- It avoids hiding drift behind one merged node that has no evidence trail.
- It keeps provenance available for debugging, trust, and automation.

## Consequences

Positive:

- Drift detection has explicit semantic layers.
- Infrastructure correlation becomes explainable rather than magical.
- Future source families can join the same model without rewriting identity.

Tradeoffs:

- Correlation logic becomes more explicit and therefore more work up front.
- Canonical assets need careful merge rules to avoid false joins.
- Queries must expose when an answer is canonical truth versus layer-specific
  evidence.

## Implementation Guidance

- Reducers own the promotion from declaration or observation records into
  canonical `CloudAsset` nodes.
- Source-local projectors should write the layer-specific records only for the
  scope generation they own.
- Canonical nodes should record which evidence layers contributed to the final
  resolved asset.
- Identity conflicts must be observable and diagnosable, not silently merged.
