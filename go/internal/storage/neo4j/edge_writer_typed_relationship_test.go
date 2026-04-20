package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestEdgeWriterWriteEdgesTypedRepoRelationshipDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":           "repo-a",
				"target_repo_id":    "repo-b",
				"relationship_type": "DEPLOYS_FROM",
				"evidence_type":     "argocd_application_source",
			},
		},
		{
			IntentID:     "i2",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":           "repo-a",
				"target_repo_id":    "repo-c",
				"relationship_type": "DISCOVERS_CONFIG_IN",
				"evidence_type":     "github_actions_reusable_workflow_ref",
			},
		},
		{
			IntentID:     "i3",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":           "repo-a",
				"target_repo_id":    "repo-d",
				"relationship_type": "PROVISIONS_DEPENDENCY_FOR",
				"evidence_type":     "terraform_module_source",
			},
		},
		{
			IntentID:     "i4",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":           "repo-a",
				"target_repo_id":    "repo-e",
				"relationship_type": "USES_MODULE",
				"evidence_type":     "terraform_module_source",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "resolver/cross-repo")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	cypher := executor.calls[0].Cypher
	for _, want := range []string{"DEPLOYS_FROM", "DISCOVERS_CONFIG_IN", "PROVISIONS_DEPENDENCY_FOR", "USES_MODULE"} {
		if !strings.Contains(cypher, want) {
			t.Fatalf("cypher missing %s branch: %s", want, cypher)
		}
	}
	rowsOut, ok := executor.calls[0].Parameters["rows"].([]map[string]any)
	if !ok {
		t.Fatalf("rows type = %T, want []map[string]any", executor.calls[0].Parameters["rows"])
	}
	for _, row := range rowsOut {
		if row["evidence_type"] == nil || row["evidence_type"] == "" {
			t.Fatalf("row missing evidence_type: %#v", row)
		}
	}
}

func TestEdgeWriterWriteEdgesRunsOnDispatchUsesWorkloadInstanceShape(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":           "repo-a",
				"platform_id":       "platform:eks:aws:cluster-1:prod:us-east-1",
				"relationship_type": "RUNS_ON",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "resolver/cross-repo")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	cypher := executor.calls[0].Cypher
	if !strings.Contains(cypher, "WorkloadInstance") {
		t.Fatalf("cypher missing WorkloadInstance match: %s", cypher)
	}
	if !strings.Contains(cypher, "MERGE (i)-[rel:RUNS_ON]->(p)") {
		t.Fatalf("cypher missing RUNS_ON merge: %s", cypher)
	}
}
