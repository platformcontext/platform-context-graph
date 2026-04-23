package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

func TestCanonicalNodeWriterSeparatesParameterizedEntityUpsertsFromContainmentEdges(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
		Files: []projector.FileRow{
			{
				Path:         "/repos/my-repo/src/main.go",
				RelativePath: "src/main.go",
				Name:         "main.go",
				Language:     "go",
				RepoID:       "repo-1",
				DirPath:      "/repos/my-repo/src",
			},
		},
		Entities: []projector.EntityRow{
			{
				EntityID:     "entity-1",
				Label:        "Function",
				EntityName:   "handleRelationships",
				FilePath:     "/repos/my-repo/src/main.go",
				RelativePath: "src/main.go",
				StartLine:    12,
				EndLine:      34,
				Language:     "go",
				RepoID:       "repo-1",
			},
			{
				EntityID:     "entity-2",
				Label:        "Function",
				EntityName:   "transitiveRelationshipsGraphResponse",
				FilePath:     "/repos/my-repo/src/main.go",
				RelativePath: "src/main.go",
				StartLine:    40,
				EndLine:      68,
				Language:     "go",
				RepoID:       "repo-1",
			},
		},
	}

	if err := writer.Write(context.Background(), mat); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	var entityUpsertCount int
	var containmentEdgeCount int
	for _, call := range exec.calls {
		if strings.Contains(call.Cypher, "MERGE (n:Function {uid: $entity_id})") {
			entityUpsertCount++
			if strings.Contains(call.Cypher, "UNWIND $rows AS row") {
				t.Fatalf("entity upsert unexpectedly still batches rows: %s", call.Cypher)
			}
			if strings.Contains(call.Cypher, "MATCH (f:File {path: row.file_path})") {
				t.Fatalf("entity upsert unexpectedly still matches File: %s", call.Cypher)
			}
			if strings.Contains(call.Cypher, "MERGE (f)-[:CONTAINS]->(n)") {
				t.Fatalf("entity upsert unexpectedly still merges containment edge: %s", call.Cypher)
			}
			if got, want := call.Parameters["entity_id"], "entity-1"; got != want && got != "entity-2" {
				t.Fatalf("entity_id = %#v, want entity-1 or entity-2", got)
			}
			if _, ok := call.Parameters["properties"].(map[string]any); !ok {
				t.Fatalf("properties type = %T, want map[string]any", call.Parameters["properties"])
			}
		}
		if strings.Contains(call.Cypher, "MATCH (f:File {path: $file_path})") &&
			strings.Contains(call.Cypher, "MATCH (n:Function {uid: $entity_id})") &&
			strings.Contains(call.Cypher, "MERGE (f)-[:CONTAINS]->(n)") {
			containmentEdgeCount++
			if got := call.Parameters["file_path"]; got != "/repos/my-repo/src/main.go" {
				t.Fatalf("containment file_path = %#v, want /repos/my-repo/src/main.go", got)
			}
			if got := call.Parameters["entity_id"]; got != "entity-1" && got != "entity-2" {
				t.Fatalf("containment entity_id = %#v, want entity-1 or entity-2", got)
			}
		}
	}

	if got, want := entityUpsertCount, 2; got != want {
		t.Fatalf("entity upsert count = %d, want %d", got, want)
	}
	if got, want := containmentEdgeCount, 2; got != want {
		t.Fatalf("containment edge count = %d, want %d", got, want)
	}
}
