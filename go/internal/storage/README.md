# Storage

`storage` contains the concrete persistence adapters for PCG.

Postgres stores facts, queue state, content, status, and recovery data. Cypher
packages define backend-neutral graph write contracts. Neo4j and NornicDB
compatibility must stay behind documented graph ports and dialect seams.

## Dependencies

This directory has no Go source of its own. Per-adapter dependencies are
documented in `storage/cypher/README.md`, `storage/postgres/README.md`,
and `storage/neo4j/README.md`.

## Telemetry

Adapter-specific telemetry is documented in each subpackage README. The
shared contract lives in `internal/telemetry`.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/nornicdb-tuning.md`
- `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`
