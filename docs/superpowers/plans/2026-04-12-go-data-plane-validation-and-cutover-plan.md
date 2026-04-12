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
- operator status surfaces can summarize queue and runtime state locally
- `go/internal/status` is exercised as the shared operator-status reader/report
  seam through the CLI without depending on an HTTP transport
- the reusable HTTP adapter for the same report seam is validated locally
  without requiring a runtime mount
- every long-running service exposes the same operator/status shape through that
  shared seam, even when some counters are service-specific
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

The current proof-domain slice is `workload_identity`, validated through the
deterministic Go harness in
`go/internal/storage/postgres/proof_domain_test.go`. That harness proves the
collector-emitted fact envelope, source-local projector, and reducer-intent
queue can drain end to end without relying on the future runtime wiring.

Known pending integration points for this slice:

- live collector process wiring into the Go ingestion store
- future cloud queue/drain plumbing for the projector and reducer services
- production canonical-write adapters for the proof-domain runtime path

### Layer 4: Cloud test-instance validation

Required before authority flip:

- the chosen proof domain runs in the cloud test environment
- no full re-index is required for ordinary source updates
- backlog, retry, and reducer behavior remain understandable under load
- CLI and API admin/status views report live progress and health meaningfully
- CLI and API admin/status views stay consistent across collector, projector,
  reducer, and future long-running services
- API and MCP reads continue to use canonical truth correctly

## Cutover Phases

### Phase 0: Documentation lock

The current step. No implementation fan-out happens before the documentation
package is accepted.

### Phase 1: Substrate green

The new Go data plane is locally healthy for one bounded path.

For the operator-status slice, "green" means the storage-agnostic report seam
exists, the CLI uses it successfully, and the shared HTTP adapter is locally
validated. It does not yet require the future runtime mount.

For later slices, "green" also means each long-running service follows the same
operator contract:

- one shared report seam
- one familiar CLI/admin shape
- live versus inferred status called out explicitly
- stage and backlog visibility that is comparable across services

### Phase 2: Proof bridge

One domain is allowed to bridge through a narrow compatibility layer while the
new substrate is proven. This is temporary and explicitly documented.

### Phase 3: Domain authority flip

The proof domain becomes owned by the new substrate. The legacy path stops
owning it.

When the future HTTP/admin transport lands, it should mount the already-tested
shared adapter from `go/internal/status` rather than introducing a second
status projection or transport-specific status path.

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
