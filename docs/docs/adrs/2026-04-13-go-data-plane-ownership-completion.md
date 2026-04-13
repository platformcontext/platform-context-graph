# ADR: Go Data Plane Ownership Completion

**Status:** Accepted

## Context

The Go data-plane rewrite proof is complete (Milestones 0-5), and the cutover
plan (`2026-04-13-go-write-plane-conversion-cutover.md`) tracks the five chunks
needed to remove Python runtime ownership from deployed services. Chunks 1 and
3 are done. Chunk 2 (native parser/collector) is in progress. Chunks 4 and 5
have Go handlers and gate tests in place but cannot close until Chunk 2
finishes.

However, the cutover plan only tracks the **deployment surface** of the
conversion. It does not cover the deeper Python write-plane modules that still
own critical resolution, projection, and operational behavior:

- `src/platform_context_graph/resolution/` (38 files) owns projection
  orchestration, platform materialization, shared projection intent processing,
  failure classification, and decision recording. Go covers only the core
  projector/reducer service loops (~20% of the resolution surface).
- `src/platform_context_graph/facts/` (26 files) owns fact storage, work queue
  lifecycle, dead-letter recovery, and replay. Go has partial equivalents in
  `go/internal/storage/postgres/` but the Python module still owns emission
  orchestration and the full claim/complete/fail lifecycle surface.
- `src/platform_context_graph/runtime/status_store*.py` (5 files) owns runtime
  status tracking, scan/reindex request lifecycle, and repository coverage
  metrics. Go has a partial equivalent in `go/internal/storage/postgres/status.go`
  but does not cover the full request lifecycle or coverage tracking.
- `src/platform_context_graph/indexing/` (23 files) owns the coordinator
  pipeline, checkpoint persistence, facts-first emission orchestration, and
  performance telemetry. This module is tightly coupled to the collector and
  cannot be ported independently of Chunk 2.

The existing ADRs establish that resolution owns cross-domain truth and that
reducers are the canonical authority for shared domains. But the Go reducer and
projector implementations currently delegate all domain-specific logic to Python.
The write-plane conversion is not honest until Go owns the domain logic, not
just the service loops.

## Decision

PCG will extend the write-plane conversion beyond the deployment cutover to
cover full Go ownership of resolution, projection, and operational surfaces.

The work is organized into three phases that can proceed independently of the
parser/collector cutover (Chunk 2):

### Phase A: Recovery and operational proxy

Wire the existing Go recovery handlers into the Python admin and CLI surfaces
so that recovery operations flow through Go immediately, even while the Python
finalization files still exist. Update documentation to reflect Go-owned
recovery.

### Phase B: Resolution domain ownership

Port the Python resolution domain logic to Go so that the projector and reducer
service loops own their domain-specific behavior end to end:

1. **Platform materialization**: port `resolution/platforms.py` and
   `resolution/platform_families.py` so Go reducers own infrastructure and
   runtime platform edge materialization.
2. **Projection decision recording**: port `resolution/decisions/` so Go
   projectors persist decision metadata and evidence natively.
3. **Shared projection intent workers**: port
   `resolution/shared_projection/runtime.py`, `emission.py`, and
   `partitioning.py` so Go owns partition-based intent draining and cross-domain
   edge materialization.
4. **Failure classification**: port
   `resolution/orchestration/failure_classification.py` so Go projector and
   reducer services own durable failure metadata.
5. **Projector fact-stage expansion**: port
   `resolution/projection/{entities,files,relationships,workloads}.py` so Go
   projectors own the full fact-to-graph/content/intent materialization for
   every projection stage.

### Phase C: Operational and validation surfaces

1. **Status store parity**: port `runtime/status_store_runtime.py` surfaces so
   Go owns scan/reindex request lifecycle and repository coverage tracking.
2. **Test infrastructure**: add build-tag isolation for `storage/postgres` tests
   so recovery and resolution tests can run independently of in-progress
   collector work.
3. **Gate tests**: extend the Chunk 5 ownership gate tests to cover resolution,
   facts, and status store Python ownership removal.
4. **Compose verification**: update compose proof scripts and add integration
   tests for the Go write-plane end-to-end path.

## Why This Choice

- The cutover plan tracks the deployment surface but not the domain logic.
  Without this extension, the branch would merge with Go service loops that
  delegate all real work to Python.
- Resolution domain logic has no dependency on Chunk 2 (parser/collector). It
  can proceed in parallel.
- The existing ADR "Resolution Owns Cross-Domain Truth" mandates that reducers
  own canonical truth. Go reducer domain handlers exist for workload identity
  and cloud asset resolution, but the platform materialization, decision
  recording, and shared projection surfaces are still Python-only.
- Porting resolution logic to Go before the final deletion phase means
  Chunks 4/5 closures will be simpler: fewer Python surfaces to rewire when
  the collector bridge is removed.

## Consequences

Positive:

- Go owns domain-specific projection and reduction logic, not just service
  loops.
- Recovery and admin operations flow through Go immediately.
- The merge bar is satisfied more honestly: no hidden Python delegation behind
  Go entrypoints.
- Future collector families (AWS, Kubernetes) land on Go-owned resolution from
  day one.

Tradeoffs:

- This extends the scope of the conversion beyond the original cutover plan.
- Resolution domain logic is complex; the platform materialization and shared
  projection intent workers in particular require careful parity validation.
- Some Python resolution surfaces are consumed by read-plane queries and will
  need narrow compatibility during transition.

## Implementation Guidance

- Follow TDD for every Go resolution domain port.
- Keep Python surfaces functional during transition; proxy or feature-gate
  rather than delete.
- Use the existing Go projector/reducer service loops as the integration points
  for new domain logic.
- Do not expand the Python resolution surface. New domain logic lands in Go.
- Update the doc set index and SOW when each phase completes.
- Phases A and B are unblocked. Phase C depends on Phase B for gate test
  coverage.

## Dependency Map

```text
Phase A (recovery proxy) ─────────────────────────── unblocked
Phase B (resolution domains) ─────────────────────── unblocked
Phase C (operational/validation) ──── depends on B ── unblocked after B

Chunk 2 (parser/collector) ───────────────────────── independent (Codex)
Chunk 4 final deletions ──────────────────────────── blocked on Chunk 2
Chunk 5 final deletions ──────────────────────────── blocked on Chunk 2 + Phase B
```
