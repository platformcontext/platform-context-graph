# Go Data Plane Validation And Cutover Plan

This document defines how the rewrite is proven locally, validated in the cloud
test environment, and cut over without leaving two long-lived write
architectures behind.

## Validation Layers

### Layer 1: Contract validation

Required before substrate fan-out:

- schema generation succeeds
- compatibility rules are enforced
- scope, generation, fact, queue, and reducer payload tests pass

### Layer 2: Local runtime validation

Required before any cloud proof:

- service bootstrap tests pass
- scope lifecycle tests pass
- queue and retry semantics pass
- projector and reducer integration tests pass
- canonical write assertions pass
- docs validation passes

### Layer 3: Proof-domain migration

Required before broader cutover:

- one existing repo-backed domain runs through the new substrate
- the end-to-end path is observable with metrics, traces, and logs
- canonical outputs match the accepted truth for that domain

### Layer 4: Cloud test-instance validation

Required before authority flip:

- the chosen proof domain runs in the cloud test environment
- no full re-index is required for ordinary source updates
- backlog, retry, and reducer behavior remain understandable under load
- API and MCP reads continue to use canonical truth correctly

## Cutover Phases

### Phase 0: Documentation lock

The current step. No implementation fan-out happens before the documentation
package is accepted.

### Phase 1: Substrate green

The new Go data plane is locally healthy for one bounded path.

### Phase 2: Proof bridge

One domain is allowed to bridge through a narrow compatibility layer while the
new substrate is proven. This is temporary and explicitly documented.

### Phase 3: Domain authority flip

The proof domain becomes owned by the new substrate. The legacy path stops
owning it.

### Phase 4: Legacy retirement

Equivalent legacy finalize behavior is removed or reduced to a clearly bounded
bridge that has an end date or milestone.

## Rollback Rules

- Rollback is allowed only to the previous authoritative domain owner.
- Rollback does not justify adding new product logic to the legacy seam.
- Every rollback must record the failure mode, the affected scope or domain,
  and the missing validation signal that would have caught it sooner.

## Exit Gate Before AWS Or Kubernetes Work

AWS and Kubernetes collectors do not begin until all of the following are true:

- scope and generation contracts are frozen
- one repo-backed domain has completed proof migration
- projector and reducer runtimes are demonstrably separate
- observability shows the full path from collection to canonical write
- the authority-flip and rollback procedure is documented and tested
