# ADR: Go Data Plane Ownership Completion

**Status:** Accepted

## Context

The Go data-plane rewrite proof is complete (Milestones 0-5), and the cutover
plan (`2026-04-13-go-write-plane-conversion-cutover.md`) tracks the five chunks
needed to remove Python runtime ownership from deployed services. Chunks 1 and
3 are done. Chunk 2 (native parser/collector) is in progress. Chunks 4 and 5
have Go handlers and gate tests in place but cannot close until Chunk 2
finishes.

However, the cutover plan only tracked the **deployment surface** of the
conversion. It did not cover the remaining ownership cleanup needed after the
Go runtime loops landed. This ADR exists to finish the migration, not to
legitimize a long-lived mixed Python/Go runtime.

Some package families called out when this ADR was written have already been
deleted from the branch. The remaining ownership debt is now more specific:

- the deployed API service still starts from the Python runtime command
  `pcg serve start`, even though a Go API binary exists in `go/cmd/api`
- Python API, MCP, and CLI orchestration still survive under
  `src/platform_context_graph/api/**`,
  `src/platform_context_graph/mcp/**`, and
  `src/platform_context_graph/cli/**`
- the legacy Python `content/ingest.py` shaping seam has now been deleted; the
  remaining Python-owned content work is read/query-side rather than normal
  runtime shaping
- parser-family ownership is now finished in the canonical contract and on
  disk; the remaining parser debt is downstream graph/materialization truth for
  Go-emitted buckets rather than missing parser scaffolding or Python parser
  entrypoints

The existing ADRs establish that resolution owns cross-domain truth and that
reducers are the canonical authority for shared domains. But the Go reducer and
projector implementations currently delegate all domain-specific logic to Python.
The write-plane conversion is not honest until Go owns the domain logic, not
just the service loops.

## Decision

PCG will extend the write-plane conversion beyond the deployment cutover to
cover full Go ownership of resolution, projection, and operational surfaces.
Python ownership remains a deletion target across the branch; it is not an
acceptable steady-state runtime dependency after merge.

The work is organized into three phases that can proceed independently of the
parser/collector cutover (Chunk 2):

### Phase A: Recovery endpoint migration

Delete the Python admin and CLI recovery endpoints (refinalize, replay) and let
the Go ingester own them directly at `/admin/replay` and `/admin/refinalize`.
The Go recovery handlers already exist and are wired into the ingester admin
mux. This is a full migration: Python recovery code is deleted, not wrapped.
Update documentation to reflect Go-owned recovery.

### Phase B: Resolution domain ownership

Finish the remaining domain-ownership cleanup so that the projector and reducer
service loops own their surviving domain-specific behavior end to end and no
deleted Python package family is accidentally reintroduced:

1. **Platform materialization**: keep Go reducers as the owner of
   infrastructure and runtime platform edge materialization.
2. **Projection decision recording**: keep Go projectors as the owner of
   persisted decision metadata and evidence.
3. **Shared projection intent workers**: keep Go as the owner of partition-
   based intent draining and cross-domain edge materialization.
4. **Failure classification**: keep Go projector and reducer services as the
   owner of durable failure metadata.
5. **Projector fact-stage expansion**: keep Go projectors as the owner of the
   fact-to-graph/content/intent materialization stages and remove any
   remaining Python-normal-path dependence.

### Phase C: Operational and validation surfaces

1. **Status store parity**: keep Go status ownership as the source of truth for
   scan/reindex request lifecycle and repository coverage tracking.
2. **Test infrastructure**: add build-tag isolation for `storage/postgres` tests
   so recovery and resolution tests can run independently of in-progress
   collector work.
3. **Gate tests**: extend the Chunk 5 ownership gate tests to cover resolution,
   facts, and status store Python ownership removal.
4. **Compose verification**: update compose proof scripts and add integration
   tests for the Go write-plane end-to-end path.

## Why This Choice

- The cutover plan tracks the deployment surface but not the remaining
  ownership debt. Without this extension, the branch would merge with
  Go-owned runtime loops plus a still-Python API/orchestration layer and an
  unfinished parser/content seam.
- Runtime/admin/recovery ownership has already moved much further than the
  original ADR snapshot assumed, and the parser-family cutover is now also
  complete, but content/API cleanup is still open.
- The existing ADR "Resolution Owns Cross-Domain Truth" still mandates that
  the canonical runtime path stay Go-owned. The remaining open work has shifted
  from deleted resolution/facts packages toward parser/content/API ownership
  closure.
- Finishing the remaining ownership cleanup before merge keeps the branch
  honest: no hidden Python delegation behind Go-owned runtime claims.

## Consequences

Positive:

- Go owns the long-running write-plane runtime, recovery, and status logic, not
  just the service loops.
- Recovery and admin operations flow through Go immediately.
- The merge bar is satisfied more honestly: no hidden Python delegation behind
  Go entrypoints.
- Future collector families (AWS, Kubernetes) land on Go-owned resolution from
  day one.

Tradeoffs:

- This extends the scope of the conversion beyond the original deployment
  cutover plan.
- Content parity and API/MCP/CLI ownership are now the harder migration
  problems than the already-landed runtime loops and parser-family cutover.
- Some Python API/MCP/CLI surfaces still need same-branch deletion or
  replacement so that the branch does not ship with broken imports into already
  deleted package families.

## Implementation Guidance

- Follow TDD for every Go resolution domain port.
- Do not preserve Python ownership as a resting state. Delete Python endpoints
  when Go owns the behavior. If a Python surface must exist briefly for
  sequencing, it must stay out of the normal runtime path and carry an explicit
  deletion condition before merge.
- Use the existing Go projector/reducer service loops as the integration points
  for new domain logic.
- Do not expand the Python resolution surface. New domain logic lands in Go.
- Update the doc set index and SOW when each phase completes.
- Phases A and B are unblocked. Phase C depends on Phase B for gate test
  coverage.

## Dependency Map

```text
Phase A (recovery migration) ────────────────────────── unblocked
Phase B (resolution domains) ─────────────────────── unblocked
Phase C (operational/validation) ──── depends on B ── unblocked after B

Chunk 2 (parser/collector) ───────────────────────── independent (Codex)
Chunk 4 final deletions ──────────────────────────── blocked on Chunk 2
Chunk 5 final deletions ──────────────────────────── blocked on Chunk 2 + Phase B
```
