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
| `specs/backend-conformance.v1.yaml` | Backend behavior classes, profile gates, and promotion status for official graph adapters. |
| `go/internal/backendconformance/` | Go harness for parsing the backend matrix and running shared read/write corpora. |

## What The Harness Covers

The default Go harness is intentionally DB-free. It proves the matrix is valid,
that it names the same official backends as the capability matrix, and that the
shared read/write corpora can run against any adapter that satisfies PCG's
graph ports.

The read corpus targets `GraphQuery`.

The write corpus targets the current Cypher executor family:

- `Executor`
- `GroupExecutor`
- `PhaseGroupExecutor`

PCG does not currently expose one concrete Go interface named `GraphWrite`.
When older ADR language says `GraphWrite`, read that as this Cypher write
executor family unless a later ADR formalizes a narrower interface.

## Live Backend Check

The live check runs the same corpus against a real Bolt endpoint. It is opt-in
so normal unit tests stay fast:

```bash
PCG_GRAPH_BACKEND=nornicdb ./scripts/verify_backend_conformance_live.sh
PCG_GRAPH_BACKEND=neo4j ./scripts/verify_backend_conformance_live.sh
```

The script defaults to the local Compose credentials and database names:
`nornic` for NornicDB and `neo4j` for Neo4j. Override the usual Bolt variables
when you are testing a different target:

```bash
PCG_GRAPH_BACKEND=nornicdb \
PCG_NEO4J_URI=bolt://localhost:7687 \
PCG_NEO4J_USERNAME=neo4j \
PCG_NEO4J_PASSWORD=change-me \
PCG_NEO4J_DATABASE=nornic \
./scripts/verify_backend_conformance_live.sh
```

GitHub Actions runs this live check in the end-to-end matrix before
`bootstrap-index`, so both official backends prove the shared read/write corpus
against a clean graph service.

## Profile Matrix

Chunk 5b is tracked in the same backend matrix under `profile_matrix`.
NornicDB must carry a gate for each profile that can use an authoritative
graph backend:

- `local_authoritative`
- `local_full_stack`
- `production`

The `local_authoritative` gate is backed by the opt-in local-host performance
tests plus the latest full-corpus API/MCP evidence. The `local_full_stack` gate
is backed by the NornicDB Compose matrix, now running with
`PCG_QUERY_PROFILE=local_full_stack`. The `production` gate stays explicit:
latest-main full-corpus evidence is healthy, but final production promotion
still needs a recorded comparison against the current Neo4j-compatible
baseline.

## Promotion Rule

Chunk 5 adds the deterministic harness, backend matrix, and live Compose-backed
adapter check. Chunk 5b records the profile-matrix proof across:

- `local_authoritative`
- `local_full_stack`
- `production`

NornicDB can remain the default while those gates close, but it is not fully
promoted until the latest-main policy, backend conformance, and profile-matrix
evidence all agree.
