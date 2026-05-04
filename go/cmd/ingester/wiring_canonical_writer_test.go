package main

import (
	"context"
	"strings"
	"testing"

	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourcecypher "github.com/platformcontext/platform-context-graph/go/internal/storage/cypher"
)

func TestConfigureIngesterCanonicalWriterInlinesContainmentForNeo4j(t *testing.T) {
	t.Parallel()

	executor := &recordingGroupChunkExecutor{}
	writer := sourcecypher.NewCanonicalNodeWriter(executor, 500, nil)
	writer = configureIngesterCanonicalWriter(writer, ingesterCanonicalWriterConfig{
		GraphBackend: runtimecfg.GraphBackendNeo4j,
	})

	if err := writer.Write(context.Background(), canonicalWriterContainmentMaterialization()); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	var inlineEntities int
	for _, stmt := range executor.groupStatements {
		if stmt.Parameters[sourcecypher.StatementMetadataPhaseKey] == sourcecypher.CanonicalPhaseEntityContainment {
			t.Fatalf("Neo4j writer emitted separate entity_containment statement: %s", stmt.Cypher)
		}
		if stmt.Parameters[sourcecypher.StatementMetadataPhaseKey] != sourcecypher.CanonicalPhaseEntities {
			continue
		}
		if strings.Contains(stmt.Cypher, "MATCH (f:File {path: $file_path})") &&
			strings.Contains(stmt.Cypher, "MERGE (f)-[rel:CONTAINS]->(n)") {
			inlineEntities++
		}
	}
	if inlineEntities != 1 {
		t.Fatalf("inline entity containment statements = %d, want 1", inlineEntities)
	}
}
