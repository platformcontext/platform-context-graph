# ADR: Go Data Plane Ownership Completion

**Status:** Accepted

## Context

The original write-plane cutover plan proved the Go service loops and the
facts-first runtime shape, but it did not yet make the branch mergeable.
This ADR captured the follow-on work required to remove the remaining Python
ownership from runtime, recovery, admin, parser, and resolution surfaces.

That ownership-completion work is now finished on this branch:

- deployed services start from Go runtime entrypoints
- parser, collector, projection, recovery, and admin ownership are Go-owned
- the Python runtime tree and compatibility bridges have been deleted
- the remaining Python files in the repository are fixture inputs used to test
  parser behavior, not live service code

## Decision

PCG treats the cutover as complete only when normal runtime ownership is
Go-owned end to end. The work recorded in this ADR was organized into three
phases and is retained here as the completion record.

### Phase A: Recovery endpoint migration

Delete the Python admin and CLI recovery endpoints and let the Go ingester own
`/admin/replay` and `/admin/refinalize` directly. This phase is complete; the
Python recovery endpoints and CLI finalize bridge were deleted rather than
wrapped.

### Phase B: Resolution domain ownership

Finish the remaining domain-ownership cleanup so that the projector and reducer
service loops own their domain-specific behavior end to end and no deleted
Python package family is accidentally reintroduced. This phase is complete.

The completion work covered:

1. platform materialization in Go reducers
2. projection decision recording in Go projectors
3. shared projection intent workers in Go
4. durable failure classification in Go projector and reducer flows
5. Go-owned fact-to-graph, content, and intent materialization stages

### Phase C: Operational and validation surfaces

Move status-store ownership, gate tests, and compose-backed proof to the Go
runtime surface. This phase is complete.

## Why This Choice

- The cutover plan tracked the deployment surface but not the remaining
  ownership debt. Without this extension, the branch would have shipped with
  Go service loops but misleadingly incomplete runtime ownership.
- The existing ADR "Resolution Owns Cross-Domain Truth" still mandates that
  the canonical runtime path stay Go-owned.
- Recording the ownership-completion work separately keeps the merge bar
  auditable instead of burying the last runtime deletions inside unrelated
  parser or deployment notes.

## Consequences

Positive:

- Go owns the long-running write-plane runtime, recovery, status, parser, and
  resolution logic, not just the service loops.
- Recovery and admin operations now flow through Go immediately.
- The merge bar is satisfied honestly: no hidden Python delegation behind
  Go entrypoints remains on the normal path.
- Future collector families can start from the locked Go-owned runtime model.

Tradeoffs:

- The cutover scope was larger than a simple runtime-entrypoint swap.
- The branch needed parser, runtime, admin, and validation cleanup to finish
  before new collector work could start without carrying migration debt
  forward.

## Implementation Guidance

The branch keeps this ADR as a guardrail for future work:

- do not preserve Python ownership as a resting state
- delete temporary migration seams instead of normalizing them
- keep new domain logic in Go service boundaries
- update the doc set and runbooks whenever ownership actually changes

## Completion Map

```text
Phase A (recovery migration) ────────────────────────── complete
Phase B (resolution domains) ────────────────────────── complete
Phase C (operational/validation) ───────────────────── complete
```
