# ADR: Cutover And Legacy Bridge

**Status:** Accepted

## Context

PCG currently has a Python-heavy write path with procedural finalization seams.
The rewrite must replace that path without allowing two long-lived architectures
to grow in parallel.

At the same time, the rewrite still needs a practical migration path so one
existing domain can prove the new substrate before the entire platform flips at
once.

## Decision

PCG will use a narrow bridge and explicit cutover model:

1. lock the architecture and contracts first
2. build the Go data-plane substrate
3. prove one existing repo-backed domain on the new substrate
4. flip ownership of that domain to the new path
5. retire the equivalent legacy finalize path

The bridge is temporary and intentionally narrow.

Rules:

- no new product features land on the legacy write seam
- no new collector work deepens the procedural finalize path
- no second long-lived queue or orchestration model is introduced as a peer to
  the new data plane
- once a domain flips, the legacy path stops owning that domain

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
