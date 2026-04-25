package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestSemanticEntityWriterConstructorsSetExclusiveWriteModes(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		got  *SemanticEntityWriter
		want semanticEntityWriteMode
	}{
		{
			name: "legacy row templates",
			got:  NewSemanticEntityWriter(&recordingExecutor{}, 0),
			want: semanticEntityWriteModeLegacyRows,
		},
		{
			name: "single-row parameterized properties",
			got:  NewSemanticEntityWriterWithParameterizedRows(&recordingExecutor{}, 0),
			want: semanticEntityWriteModeParameterizedRows,
		},
		{
			name: "batched property maps",
			got:  NewSemanticEntityWriterWithBatchedProperties(&recordingExecutor{}, 0),
			want: semanticEntityWriteModeBatchedProperties,
		},
	}

	for _, tt := range tests {
		if tt.got.writeMode != tt.want {
			t.Fatalf("%s writeMode = %v, want %v", tt.name, tt.got.writeMode, tt.want)
		}
	}
}

func TestSemanticEntityWriterWithParameterizedRowsAvoidsInlineSemanticMetadata(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewSemanticEntityWriterWithParameterizedRows(executor, 0)

	const docstring = "buildCallChainCypher uses shortestPath((start)-[*]->(end)) for graph traversal."

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows: []reducer.SemanticEntityRow{
			{
				RepoID:       "repo-1",
				EntityID:     "function-go-1",
				EntityType:   "Function",
				EntityName:   "buildCallChainCypher",
				FilePath:     "/repo/go/internal/query/code_call_chain.go",
				RelativePath: "go/internal/query/code_call_chain.go",
				Language:     "go",
				StartLine:    22,
				EndLine:      178,
				Metadata: map[string]any{
					"docstring":     docstring,
					"class_context": "CodeHandler",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 1; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}

	stmt := executor.calls[1]
	if strings.Contains(stmt.Cypher, "shortestPath") {
		t.Fatalf("upsert cypher inlined shortestPath metadata: %s", stmt.Cypher)
	}
	if !strings.Contains(stmt.Cypher, "SET n += $properties") {
		t.Fatalf("upsert cypher = %q, want parameterized properties merge", stmt.Cypher)
	}
	if got, want := stmt.Parameters["entity_id"], "function-go-1"; got != want {
		t.Fatalf("entity_id = %#v, want %#v", got, want)
	}
	properties, ok := stmt.Parameters["properties"].(map[string]any)
	if !ok {
		t.Fatalf("properties type = %T, want map[string]any", stmt.Parameters["properties"])
	}
	if got, want := properties["docstring"], docstring; got != want {
		t.Fatalf("properties[docstring] = %#v, want %#v", got, want)
	}
	if got, want := properties["class_context"], "CodeHandler"; got != want {
		t.Fatalf("properties[class_context] = %#v, want %#v", got, want)
	}
}
