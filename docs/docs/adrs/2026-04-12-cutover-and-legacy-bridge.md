# ADR: Cutover And Legacy Bridge

**Status:** Accepted

## Context

PCG started the Go rewrite with Python-owned write, parser, and recovery
seams. This ADR recorded the rule that those seams were temporary and could not
turn into a second long-lived architecture.

That bridge work is now finished on this branch. The ADR remains as the record
of the transition rule that governed the cutover.

## Decision

PCG used a narrow bridge and explicit cutover model:

1. lock the architecture and contracts first
2. build the Go data-plane substrate
3. prove one existing repo-backed domain on the new substrate
4. flip ownership of that domain to the new path
5. retire the equivalent legacy finalize and parser bridge paths

The bridge was temporary and intentionally narrow.

Rules:

- no new product features land on the legacy write seam
- no new collector work deepens the procedural finalize path or parser bridge
- no second long-lived queue or orchestration model is introduced as a peer to
  the new data plane
- once a domain flips, the legacy path stops owning that domain

Current branch status:

- the Go runtime, admin/status, projection, parser, and recovery surfaces are
  in place
- the Git write plane no longer uses Python bridge ownership on the normal path
- the legacy finalize, parser, and coordinator bridge paths have been deleted
- the remaining work on the branch is parity hardening and validation, not
  preservation of a mixed-runtime design

## Why This Choice

- It gave the rewrite a real proof path without locking the team into dual
  maintenance.
- It reduced the risk of endless "temporary" compatibility work.
- It kept the architectural direction honest for future collectors.

## Consequences

Positive:

- The branch keeps one clear destination architecture.
- Migration progress stayed measurable domain by domain.
- Future workers can see that temporary bridges must be deleted, not polished.

Tradeoffs:

- Transitional code had to stay deliberately small and short-lived.
- Cutover criteria had to be explicit and enforced to prevent drift.

## Implementation Guidance

- Document every bridged behavior and the date or milestone when it is expected
  to disappear.
- Keep bridge code isolated in clearly named compatibility packages.
- Treat any request to add new logic to the old finalize seam as a design
  exception that must be justified in writing.
- Remove bridge code as soon as the new domain proof is complete and stable.

## Git Write-Plane Bridge Inventory

The legacy post-commit bridge has been systematically deleted as Go took
ownership.

Go-owned surfaces:

- recovery operations are owned by the Go ingester at `/admin/refinalize` and
  `/admin/replay`
- the deprecated `pcg finalize` command no longer routes through a Python
  helper
- parser, snapshot, bootstrap, watch-refresh, and ecosystem indexing flows are
  Go-owned on the normal path

Deleted bridge families:

- Python admin recovery endpoints
- Python CLI finalize bridge
- Python post-commit/finalization coordination modules
- Python parser/coordinator runtime ownership on the normal path

Python indexing now fails closed unless the facts-first runtime is available.
This branch no longer carries Python service ownership on the normal path.
