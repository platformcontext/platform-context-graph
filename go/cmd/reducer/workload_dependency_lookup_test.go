package main

import (
	"context"
	"strings"
	"testing"
	"time"
)

func TestWorkloadDependencyLookupListsExistingEdgesByRepoAndEvidenceSource(t *testing.T) {
	t.Parallel()

	reader := &recordingWorkloadDependencyGraphReader{
		rows: []map[string]any{
			{
				"repo_id":            "repo-a",
				"workload_id":        "workload:svc-a",
				"target_workload_id": "workload:svc-b",
			},
		},
	}
	lookup := neo4jWorkloadDependencyLookup{reader: reader}

	rows, err := lookup.ListWorkloadDependencyEdges(
		context.Background(),
		[]string{"repo-a"},
		"finalization/workloads",
	)
	if err != nil {
		t.Fatalf("ListWorkloadDependencyEdges() error = %v", err)
	}

	if got, want := len(rows), 1; got != want {
		t.Fatalf("len(rows) = %d, want %d", got, want)
	}
	if got, want := rows[0].RepoID, "repo-a"; got != want {
		t.Fatalf("rows[0].RepoID = %q, want %q", got, want)
	}
	if got, want := rows[0].WorkloadID, "workload:svc-a"; got != want {
		t.Fatalf("rows[0].WorkloadID = %q, want %q", got, want)
	}
	if got, want := rows[0].TargetWorkloadID, "workload:svc-b"; got != want {
		t.Fatalf("rows[0].TargetWorkloadID = %q, want %q", got, want)
	}
	if !strings.Contains(reader.cypher, "MATCH (source:Workload)-[rel:DEPENDS_ON]->(target:Workload)") {
		t.Fatalf("cypher = %q, want workload dependency match", reader.cypher)
	}
	if !strings.Contains(reader.cypher, "source.repo_id IN $repo_ids") {
		t.Fatalf("cypher = %q, want repo_id predicate", reader.cypher)
	}
	if got, want := reader.params["evidence_source"], "finalization/workloads"; got != want {
		t.Fatalf("evidence_source param = %#v, want %#v", got, want)
	}
}

type recordingWorkloadDependencyGraphReader struct {
	cypher string
	params map[string]any
	rows   []map[string]any
}

func (r *recordingWorkloadDependencyGraphReader) Run(
	_ context.Context,
	cypher string,
	params map[string]any,
) ([]map[string]any, error) {
	r.cypher = cypher
	r.params = params
	return append([]map[string]any(nil), r.rows...), nil
}

func (r *recordingWorkloadDependencyGraphReader) RunSingle(
	context.Context,
	string,
	map[string]any,
) (map[string]any, error) {
	return nil, nil
}

func (r *recordingWorkloadDependencyGraphReader) RelationshipTypes(context.Context) ([]string, error) {
	return nil, nil
}

func (r *recordingWorkloadDependencyGraphReader) Close(context.Context) error {
	return nil
}

func (r *recordingWorkloadDependencyGraphReader) LastQueryDuration() time.Duration {
	return 0
}
