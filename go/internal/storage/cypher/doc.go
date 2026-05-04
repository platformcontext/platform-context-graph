// Package cypher owns backend-neutral Cypher write contracts, canonical
// node and edge writers, statement metadata, and write instrumentation for
// PCG's canonical graph.
//
// Writers in this package emit Cypher that runs against any supported
// graph backend through the GraphWrite port. Dialect-specific behavior
// must stay narrow and explicit: schema adapters, writer options, and
// query builders own backend differences so callers do not need to branch
// on PCG_GRAPH_BACKEND. Writes must be idempotent and retry-safe; the
// canonical writers are the boundary where node and edge invariants are
// enforced before bytes reach Neo4j or NornicDB.
package cypher
