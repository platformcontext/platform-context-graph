# Backend Conformance

`backendconformance` owns the reusable graph-backend proof harness.

The package keeps two contracts together:

- the machine-readable backend matrix in `specs/backend-conformance.v1.yaml`
- the read and write corpora used to exercise `GraphQuery` and Cypher executor
  adapters

Default Go tests validate the matrix and harness without starting Neo4j or
NornicDB. Live backend runs can reuse the same corpora from integration tests,
Compose proofs, or remote validation.
