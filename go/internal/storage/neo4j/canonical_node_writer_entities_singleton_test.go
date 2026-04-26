package neo4j

import (
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

func TestCanonicalNodeWriterFileScopedContainmentUsesSingletonForOneRow(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil).
		WithEntityContainmentInEntityUpsert().
		WithEntityLabelBatchSize("K8sResource", 1)
	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Entities: []projector.EntityRow{
			{
				EntityID:     "k8s-1",
				Label:        "K8sResource",
				EntityName:   "route",
				FilePath:     "/repos/my-repo/charts/routes.yaml",
				RelativePath: "charts/routes.yaml",
				StartLine:    1,
				EndLine:      1,
				Language:     "yaml",
				RepoID:       "repo-1",
			},
		},
	}

	stmts := writer.buildEntityStatements(mat)
	if got, want := len(stmts), 1; got != want {
		t.Fatalf("buildEntityStatements() count = %d, want %d", got, want)
	}
	stmt := stmts[0]
	if strings.Contains(stmt.Cypher, "UNWIND $rows AS row") {
		t.Fatalf("entity cypher = %q, want singleton shape without UNWIND", stmt.Cypher)
	}
	if got, want := stmt.Parameters[StatementMetadataPhaseGroupModeKey], PhaseGroupModeExecuteOnly; got != want {
		t.Fatalf("phase group mode = %#v, want %#v", got, want)
	}
	if got, want := stmt.Parameters["entity_id"], "k8s-1"; got != want {
		t.Fatalf("entity_id = %#v, want %#v", got, want)
	}
}
