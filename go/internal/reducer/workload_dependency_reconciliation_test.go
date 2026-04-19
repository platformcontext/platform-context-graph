package reducer

import (
	"context"
	"reflect"
	"testing"
)

type fakeWorkloadDependencyGraphLookup struct {
	repoEdges          []RepoDependencyEdge
	workloads          []RepoWorkload
	repoEdgeRepoIDs    []string
	repoWorkloadRepoIDs []string
}

func (f *fakeWorkloadDependencyGraphLookup) ListRepoDependencyEdges(
	_ context.Context,
	repoIDs []string,
) ([]RepoDependencyEdge, error) {
	f.repoEdgeRepoIDs = append([]string(nil), repoIDs...)
	return append([]RepoDependencyEdge(nil), f.repoEdges...), nil
}

func (f *fakeWorkloadDependencyGraphLookup) ListRepoWorkloads(
	_ context.Context,
	repoIDs []string,
) ([]RepoWorkload, error) {
	f.repoWorkloadRepoIDs = append([]string(nil), repoIDs...)
	return append([]RepoWorkload(nil), f.workloads...), nil
}

func TestReconcileWorkloadDependencyEdgesBuildsAuthoritativeAndIncomingRows(t *testing.T) {
	t.Parallel()

	lookup := &fakeWorkloadDependencyGraphLookup{
		repoEdges: []RepoDependencyEdge{
			{SourceRepoID: "repo-a", TargetRepoID: "repo-b"},
			{SourceRepoID: "repo-c", TargetRepoID: "repo-a"},
		},
		workloads: []RepoWorkload{
			{RepoID: "repo-a", WorkloadID: "workload:svc-a"},
			{RepoID: "repo-b", WorkloadID: "workload:svc-b"},
			{RepoID: "repo-c", WorkloadID: "workload:svc-c"},
		},
	}

	rows, retractRows, err := ReconcileWorkloadDependencyEdges(
		context.Background(),
		[]RepoDescriptor{{RepoID: "repo-a", RepoName: "svc-a", WorkloadID: "workload:svc-a"}},
		lookup,
	)
	if err != nil {
		t.Fatalf("ReconcileWorkloadDependencyEdges() error = %v", err)
	}

	if got, want := len(retractRows), 1; got != want {
		t.Fatalf("len(retractRows) = %d, want %d", got, want)
	}
	if got, want := retractRows[0].RepositoryID, "repo-a"; got != want {
		t.Fatalf("retractRows[0].RepositoryID = %q, want %q", got, want)
	}

	wantRows := []WorkloadDependencyEdgeRow{
		{
			RepoID:           "repo-a",
			WorkloadID:       "workload:svc-a",
			TargetRepoID:     "repo-b",
			TargetWorkloadID: "workload:svc-b",
		},
		{
			RepoID:           "repo-c",
			WorkloadID:       "workload:svc-c",
			TargetRepoID:     "repo-a",
			TargetWorkloadID: "workload:svc-a",
		},
	}
	if !reflect.DeepEqual(rows, wantRows) {
		t.Fatalf("rows = %#v, want %#v", rows, wantRows)
	}
	if !reflect.DeepEqual(lookup.repoEdgeRepoIDs, []string{"repo-a"}) {
		t.Fatalf("repoEdgeRepoIDs = %#v, want %#v", lookup.repoEdgeRepoIDs, []string{"repo-a"})
	}
	if !reflect.DeepEqual(lookup.repoWorkloadRepoIDs, []string{"repo-a", "repo-b", "repo-c"}) {
		t.Fatalf("repoWorkloadRepoIDs = %#v, want %#v", lookup.repoWorkloadRepoIDs, []string{"repo-a", "repo-b", "repo-c"})
	}
}

func TestReconcileWorkloadDependencyEdgesSkipsAmbiguousRepos(t *testing.T) {
	t.Parallel()

	lookup := &fakeWorkloadDependencyGraphLookup{
		repoEdges: []RepoDependencyEdge{
			{SourceRepoID: "repo-a", TargetRepoID: "repo-b"},
			{SourceRepoID: "repo-c", TargetRepoID: "repo-a"},
		},
		workloads: []RepoWorkload{
			{RepoID: "repo-a", WorkloadID: "workload:svc-a"},
			{RepoID: "repo-a", WorkloadID: "workload:svc-a-worker"},
			{RepoID: "repo-b", WorkloadID: "workload:svc-b"},
			{RepoID: "repo-c", WorkloadID: "workload:svc-c"},
		},
	}

	rows, retractRows, err := ReconcileWorkloadDependencyEdges(
		context.Background(),
		[]RepoDescriptor{
			{RepoID: "repo-a", RepoName: "svc-a", WorkloadID: "workload:svc-a"},
			{RepoID: "repo-a", RepoName: "svc-a-worker", WorkloadID: "workload:svc-a-worker"},
		},
		lookup,
	)
	if err != nil {
		t.Fatalf("ReconcileWorkloadDependencyEdges() error = %v", err)
	}

	if len(rows) != 0 {
		t.Fatalf("rows = %#v, want empty for ambiguous repo", rows)
	}
	if got, want := len(retractRows), 1; got != want {
		t.Fatalf("len(retractRows) = %d, want %d", got, want)
	}
}

func TestBuildWorkloadDependencyIntentRowsFromEdges(t *testing.T) {
	t.Parallel()

	rows := BuildWorkloadDependencyIntentRowsFromEdges([]WorkloadDependencyEdgeRow{
		{
			RepoID:           "repo-a",
			WorkloadID:       "workload:svc-a",
			TargetRepoID:     "repo-b",
			TargetWorkloadID: "workload:svc-b",
		},
	})
	if got, want := len(rows), 1; got != want {
		t.Fatalf("len(rows) = %d, want %d", got, want)
	}

	row := rows[0]
	if got, want := row.RepositoryID, "repo-a"; got != want {
		t.Fatalf("RepositoryID = %q, want %q", got, want)
	}
	if got, want := payloadStringAny(row.Payload, "workload_id"), "workload:svc-a"; got != want {
		t.Fatalf("payload.workload_id = %q, want %q", got, want)
	}
	if got, want := payloadStringAny(row.Payload, "target_workload_id"), "workload:svc-b"; got != want {
		t.Fatalf("payload.target_workload_id = %q, want %q", got, want)
	}
}

func payloadStringAny(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	value, ok := payload[key]
	if !ok {
		return ""
	}
	str, _ := value.(string)
	return str
}
