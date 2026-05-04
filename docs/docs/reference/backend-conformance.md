# Backend Conformance

Backend conformance is the gate that keeps graph adapters honest.

PCG supports two official graph backends today:

- NornicDB, the default backend
- Neo4j, the compatibility backend

Both backends serve the same user-facing API and MCP capabilities. They do not
get to be called supported just because they accept Cypher. They have to pass
the same contract checks for reads, writes, traversal shape, dead-code
readiness, and performance evidence.

## Files

| File | Purpose |
| --- | --- |
| `specs/capability-matrix.v1.yaml` | User-facing capability and truth contract by runtime profile. |
| `specs/backend-conformance.v1.yaml` | Backend behavior classes and promotion status for official graph adapters. |
| `go/internal/backendconformance/` | Go harness for parsing the backend matrix and running shared read/write corpora. |

## What The Harness Covers

The default Go harness is intentionally DB-free. It proves that the matrix is
valid, that it names the same official backends as the capability matrix, and
that the shared read/write corpora can run against any adapter that satisfies
PCG's graph ports.

The read corpus targets `GraphQuery`.

The write corpus targets the current Cypher executor family:

- `Executor`
- `GroupExecutor`
- `PhaseGroupExecutor`

PCG does not currently expose one concrete Go interface named `GraphWrite`.
When older ADR language says `GraphWrite`, read that as this Cypher write
executor family unless a later ADR formalizes a narrower interface.

## Promotion Rule

Chunk 5 adds the deterministic harness and backend matrix. Chunk 5b is still
the live profile-matrix proof across:

- `local_authoritative`
- `local_full_stack`
- `production`

NornicDB can remain the default while those gates close, but it is not fully
promoted until the latest-main policy, backend conformance, and profile-matrix
evidence all agree.
