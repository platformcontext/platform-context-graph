package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestSemanticEntityWriterWritesAnnotationAndTypedefNodes(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewSemanticEntityWriter(executor, 0)

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows: []reducer.SemanticEntityRow{
			{
				RepoID:       "repo-1",
				EntityID:     "annotation-1",
				EntityType:   "Annotation",
				EntityName:   "Logged",
				FilePath:     "/repo/src/Logged.java",
				RelativePath: "src/Logged.java",
				Language:     "java",
				StartLine:    12,
				EndLine:      12,
				Metadata: map[string]any{
					"kind":        "applied",
					"target_kind": "method_declaration",
				},
			},
			{
				RepoID:       "repo-1",
				EntityID:     "typedef-1",
				EntityType:   "Typedef",
				EntityName:   "my_int",
				FilePath:     "/repo/src/types.h",
				RelativePath: "src/types.h",
				Language:     "c",
				StartLine:    3,
				EndLine:      3,
				Metadata: map[string]any{
					"type": "int",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 2; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 3; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if executor.calls[0].Operation != OperationCanonicalRetract {
		t.Fatalf("call[0].Operation = %q, want %q", executor.calls[0].Operation, OperationCanonicalRetract)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DETACH DELETE n") {
		t.Fatalf("call[0].Cypher missing DETACH DELETE: %s", executor.calls[0].Cypher)
	}

	annotationRows := executor.calls[1].Parameters["rows"].([]map[string]any)
	if got, want := len(annotationRows), 1; got != want {
		t.Fatalf("annotation row count = %d, want %d", got, want)
	}
	if got, want := annotationRows[0]["kind"], "applied"; got != want {
		t.Fatalf("annotation kind = %#v, want %#v", got, want)
	}
	if got, want := annotationRows[0]["target_kind"], "method_declaration"; got != want {
		t.Fatalf("annotation target_kind = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[1].Cypher, "MERGE (n:Annotation {uid: row.entity_id})") {
		t.Fatalf("annotation cypher missing Annotation merge: %s", executor.calls[1].Cypher)
	}

	typedefRows := executor.calls[2].Parameters["rows"].([]map[string]any)
	if got, want := len(typedefRows), 1; got != want {
		t.Fatalf("typedef row count = %d, want %d", got, want)
	}
	if got, want := typedefRows[0]["type"], "int"; got != want {
		t.Fatalf("typedef type = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[2].Cypher, "MERGE (n:Typedef {uid: row.entity_id})") {
		t.Fatalf("typedef cypher missing Typedef merge: %s", executor.calls[2].Cypher)
	}
}

func TestSemanticEntityWriterRetractsWithoutUpserts(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewSemanticEntityWriter(executor, 0)

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1", "repo-2"},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 0; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if executor.calls[0].Operation != OperationCanonicalRetract {
		t.Fatalf("call[0].Operation = %q, want %q", executor.calls[0].Operation, OperationCanonicalRetract)
	}
	repoIDs, ok := executor.calls[0].Parameters["repo_ids"].([]string)
	if !ok {
		t.Fatalf("repo_ids type = %T, want []string", executor.calls[0].Parameters["repo_ids"])
	}
	if got, want := len(repoIDs), 2; got != want {
		t.Fatalf("repo_ids length = %d, want %d", got, want)
	}
}
