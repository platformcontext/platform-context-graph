package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

type fakeCrossRepoEvidenceLoader struct {
	facts []relationships.EvidenceFact
}

func (f *fakeCrossRepoEvidenceLoader) ListEvidenceFacts(
	_ context.Context,
	_ string,
) ([]relationships.EvidenceFact, error) {
	return f.facts, nil
}

type recordingIntentWriter struct {
	rows [][]reducer.SharedProjectionIntentRow
}

func (r *recordingIntentWriter) UpsertIntents(
	_ context.Context,
	rows []reducer.SharedProjectionIntentRow,
) error {
	copied := make([]reducer.SharedProjectionIntentRow, len(rows))
	copy(copied, rows)
	r.rows = append(r.rows, copied)
	return nil
}

func TestCrossRepoResolutionDispatchesTypedRelationshipsIntoNeo4jWrites(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.99,
		},
		{
			EvidenceKind:     relationships.EvidenceKindHelmChart,
			RelationshipType: relationships.RelDeploysFrom,
			SourceRepoID:     "deploy-repo",
			TargetRepoID:     "config-repo",
			Confidence:       0.97,
		},
		{
			EvidenceKind:     relationships.EvidenceKindArgoCDApplicationSetDiscovery,
			RelationshipType: relationships.RelDiscoversConfigIn,
			SourceRepoID:     "control-repo",
			TargetRepoID:     "shared-config-repo",
			Confidence:       0.96,
		},
		{
			EvidenceKind:     relationships.EvidenceKindArgoCDDestinationPlatform,
			RelationshipType: relationships.RelRunsOn,
			SourceRepoID:     "service-repo",
			TargetEntityID:   "platform:eks:aws:cluster-1:prod:us-east-1",
			Confidence:       0.98,
		},
	}

	intentWriter := &recordingIntentWriter{}
	executor := &recordingExecutor{}
	handler := reducer.CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeCrossRepoEvidenceLoader{facts: evidence},
		IntentWriter:   intentWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 4 {
		t.Fatalf("Resolve() = %d, want 4", count)
	}

	if got, want := len(intentWriter.rows), 1; got != want {
		t.Fatalf("intent writes = %d, want %d", got, want)
	}
	intents := intentWriter.rows[0]
	if got, want := len(intents), 4; got != want {
		t.Fatalf("intent row count = %d, want %d", got, want)
	}

	writer := NewEdgeWriter(executor, 0)
	if err := writer.WriteEdges(
		context.Background(),
		reducer.DomainRepoDependency,
		intents,
		"resolver/cross-repo",
	); err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}

	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}

	var typedRepoWrite *Statement
	var runsOnWrite *Statement
	for i := range executor.calls {
		call := &executor.calls[i]
		switch {
		case strings.Contains(call.Cypher, "MERGE (i)-[rel:RUNS_ON]->(p)"):
			runsOnWrite = call
		case strings.Contains(call.Cypher, "DEPLOYS_FROM") ||
			strings.Contains(call.Cypher, "DISCOVERS_CONFIG_IN") ||
			strings.Contains(call.Cypher, "PROVISIONS_DEPENDENCY_FOR"):
			typedRepoWrite = call
		}
	}

	if typedRepoWrite == nil {
		t.Fatal("typed repo write call not found")
	}
	if typedRepoWrite.Operation != OperationCanonicalUpsert {
		t.Fatalf("typed repo write operation = %q, want %q", typedRepoWrite.Operation, OperationCanonicalUpsert)
	}
	if !strings.Contains(typedRepoWrite.Cypher, "DEPLOYS_FROM") {
		t.Fatalf("typed repo cypher missing DEPLOYS_FROM branch: %s", typedRepoWrite.Cypher)
	}
	if !strings.Contains(typedRepoWrite.Cypher, "DISCOVERS_CONFIG_IN") {
		t.Fatalf("typed repo cypher missing DISCOVERS_CONFIG_IN branch: %s", typedRepoWrite.Cypher)
	}
	if !strings.Contains(typedRepoWrite.Cypher, "PROVISIONS_DEPENDENCY_FOR") {
		t.Fatalf("typed repo cypher missing PROVISIONS_DEPENDENCY_FOR branch: %s", typedRepoWrite.Cypher)
	}

	typedRows, ok := typedRepoWrite.Parameters["rows"].([]map[string]any)
	if !ok {
		t.Fatalf("typed repo rows type = %T, want []map[string]any", typedRepoWrite.Parameters["rows"])
	}
	if got, want := len(typedRows), 3; got != want {
		t.Fatalf("len(typed repo rows) = %d, want %d", got, want)
	}

	gotRepoTypes := map[string]bool{}
	gotEvidenceTypes := map[string]bool{}
	for _, row := range typedRows {
		relType, _ := row["relationship_type"].(string)
		gotRepoTypes[relType] = true
		evidenceType, _ := row["evidence_type"].(string)
		if evidenceType != "" {
			gotEvidenceTypes[evidenceType] = true
		}
	}
	for _, want := range []string{
		string(relationships.RelProvisionsDependencyFor),
		string(relationships.RelDeploysFrom),
		string(relationships.RelDiscoversConfigIn),
	} {
		if !gotRepoTypes[want] {
			t.Fatalf("typed repo rows missing relationship_type %q", want)
		}
	}
	for _, want := range []string{"terraform_app_repo", "helm_chart_reference", "argocd_applicationset_discovery"} {
		if !gotEvidenceTypes[want] {
			t.Fatalf("typed repo rows missing evidence_type %q", want)
		}
	}

	if runsOnWrite == nil {
		t.Fatal("runs_on write call not found")
	}
	if runsOnWrite.Operation != OperationCanonicalUpsert {
		t.Fatalf("runs_on write operation = %q, want %q", runsOnWrite.Operation, OperationCanonicalUpsert)
	}
	if !strings.Contains(runsOnWrite.Cypher, "MERGE (i)-[rel:RUNS_ON]->(p)") {
		t.Fatalf("runs_on cypher missing RUNS_ON merge: %s", runsOnWrite.Cypher)
	}
	if !strings.Contains(runsOnWrite.Cypher, "WorkloadInstance") {
		t.Fatalf("runs_on cypher missing WorkloadInstance match: %s", runsOnWrite.Cypher)
	}

	runsOnRows, ok := runsOnWrite.Parameters["rows"].([]map[string]any)
	if !ok {
		t.Fatalf("runs_on rows type = %T, want []map[string]any", runsOnWrite.Parameters["rows"])
	}
	if got, want := len(runsOnRows), 1; got != want {
		t.Fatalf("len(runs_on rows) = %d, want %d", got, want)
	}
	if got, want := runsOnRows[0]["repo_id"], "service-repo"; got != want {
		t.Fatalf("runs_on repo_id = %#v, want %#v", got, want)
	}
	if got, want := runsOnRows[0]["platform_id"], "platform:eks:aws:cluster-1:prod:us-east-1"; got != want {
		t.Fatalf("runs_on platform_id = %#v, want %#v", got, want)
	}
}
