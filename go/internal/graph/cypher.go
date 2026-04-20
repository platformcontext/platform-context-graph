package graph

import "context"

// CypherStatement captures one executable Cypher statement with its
// parameters. This is the graph-package equivalent of the storage/neo4j
// Statement type, defined here to avoid an import cycle between graph
// and storage/neo4j.
type CypherStatement struct {
	Cypher     string
	Parameters map[string]any
}

// CypherExecutor executes Cypher statements against a Neo4j database.
// Implementations may be the real Neo4j driver or a recording mock for
// tests. This mirrors the storage/neo4j Executor interface but lives in
// the graph package to avoid import cycles.
type CypherExecutor interface {
	ExecuteCypher(context.Context, CypherStatement) error
}
