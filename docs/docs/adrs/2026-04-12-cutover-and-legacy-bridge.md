# ADR: Cutover And Legacy Bridge

**Status:** Accepted

## Context

PCG currently has Python-heavy write and parser/runtime seams with procedural
finalization and content-shaping paths. The rewrite must replace those paths
without allowing two long-lived architectures to grow in parallel. The
architecture proof package is in place, but the actual Git write-plane and
parser-platform cutovers are still incomplete on this branch.

At the same time, the rewrite still needs a practical migration path so one
existing domain can prove the new substrate before the entire platform flips at
once.

## Decision

PCG will use a narrow bridge and explicit cutover model:

1. lock the architecture and contracts first
2. build the Go data-plane substrate
3. prove one existing repo-backed domain on the new substrate
4. flip ownership of that domain to the new path
5. retire the equivalent legacy finalize and parser bridge paths

The bridge is temporary and intentionally narrow.

Rules:

- no new product features land on the legacy write seam
- no new collector work deepens the procedural finalize path or the parser
  bridge path
- no second long-lived queue or orchestration model is introduced as a peer to
  the new data plane
- once a domain flips, the legacy path stops owning that domain

Current branch status:

- the Go runtime, admin/status, projection, and recovery surfaces are in place
- the Git write plane no longer uses Python bridge ownership for selection,
  snapshot collection, local bootstrap indexing, local watch refreshes, or
  ecosystem manifest indexing on the normal path
- the parser, discovery, and content-shaping path still has Python ownership on
  the remaining uncovered portions of the normal runtime path
- no new ingestor family should start until the Python runtime ownership is
  fully removed and the cutover is proven end to end

## Why This Choice

- It gives the rewrite a real proof path without locking the team into dual
  maintenance.
- It reduces the risk of endless "temporary" compatibility work.
- It keeps the architectural direction honest for future collectors.

## Consequences

Positive:

- The branch keeps one clear destination architecture.
- Migration progress is measurable domain by domain.
- Future workers know which path is authoritative.

Tradeoffs:

- Transitional code must stay deliberately small.
- Cutover criteria must be explicit and enforced.

## Implementation Guidance

- Document every bridged behavior and the date or milestone when it is expected
  to disappear.
- Keep bridge code isolated in clearly named compatibility packages.
- Treat any request to add new logic to the old finalize seam as a design
  exception that must be justified in writing.
- Remove bridge code as soon as the new domain proof is complete and stable.

## Git Write-Plane Bridge Inventory

The legacy post-commit bridge is being systematically deleted as Go takes
ownership. Current status:

**Go-owned (Python endpoints deleted):**

- Recovery operations (refinalize, replay) are owned by the Go ingester at
  `/admin/refinalize` and `/admin/replay`. The Python admin endpoints in
  `api/routers/admin.py` and `api/routers/admin_facts.py` have been deleted.
- `src/platform_context_graph/cli/helpers/finalize.py` has been deleted. The
  `pcg finalize` CLI command prints a deprecation message directing operators
  to the Go ingester admin surface.

**Deleted on this branch:**

- `src/platform_context_graph/indexing/post_commit_writer.py`
- `src/platform_context_graph/collectors/git/finalize.py`
- `src/platform_context_graph/indexing/coordinator_finalize.py`

Python indexing now fails closed unless the facts-first runtime is available.
The remaining ownership blockers have moved forward to parser-matrix
completion, the surviving Python `content/ingest.py` seam, and the still-live
Python API/MCP/CLI orchestration surfaces tracked in the ownership completion
plan.
