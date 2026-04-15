package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestSemanticEntityWriterWritesTSXFunctionFragmentMetadata(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewSemanticEntityWriter(executor, 0)

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows: []reducer.SemanticEntityRow{
			{
				RepoID:       "repo-1",
				EntityID:     "function-tsx-1",
				EntityType:   "Function",
				EntityName:   "Screen",
				FilePath:     "/repo/src/Screen.tsx",
				RelativePath: "src/Screen.tsx",
				Language:     "tsx",
				StartLine:    7,
				EndLine:      14,
				Metadata: map[string]any{
					"jsx_fragment_shorthand": true,
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v, want nil", err)
	}
	if got, want := result.CanonicalWrites, 1; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}

	functionRows := executor.calls[1].Parameters["rows"].([]map[string]any)
	if got, want := len(functionRows), 1; got != want {
		t.Fatalf("function row count = %d, want %d", got, want)
	}
	if got, want := functionRows[0]["jsx_fragment_shorthand"], true; got != want {
		t.Fatalf("function jsx_fragment_shorthand = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[1].Cypher, "n.jsx_fragment_shorthand = row.jsx_fragment_shorthand") {
		t.Fatalf("function cypher missing jsx_fragment_shorthand assignment: %s", executor.calls[1].Cypher)
	}
}
