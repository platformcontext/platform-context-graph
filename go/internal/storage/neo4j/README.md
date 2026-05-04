# Neo4j Storage

`storage/neo4j` owns Neo4j-specific graph adapters and driver integration.

Neo4j remains an officially supported graph backend. Keep its behavior aligned
with the graph ports so NornicDB compatibility work does not accidentally fork
the public query or write contracts.

## Dependencies

No internal package imports today; the package currently holds only
`doc.go` while the Bolt session adapter is being narrowed out of
`internal/runtime`. Backend-neutral writers live in
`internal/storage/cypher`.

## Telemetry

Inherits from `internal/telemetry`; this package does not emit its own
metrics or spans. Driver-level telemetry is handled by the runtime
bootstrap until the Bolt adapter moves here.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`
- `docs/docs/adrs/2026-04-20-embedded-local-backends-implementation-plan.md`
