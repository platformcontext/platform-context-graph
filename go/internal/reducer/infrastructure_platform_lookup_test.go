package reducer

import (
	"context"
	"strings"
	"testing"
)

func TestGraphInfrastructurePlatformLookupListsProvisionedPlatforms(t *testing.T) {
	t.Parallel()

	graph := &stubGraphQueryRunner{
		rows: []map[string]any{
			{
				"repo_id":           "repo-infra",
				"platform_id":       "platform:ecs:aws:cluster/runtime-main:none:none",
				"platform_name":     "runtime-main",
				"platform_kind":     "ecs",
				"platform_provider": "aws",
				"platform_locator":  "cluster/runtime-main",
			},
			{
				"repo_id":       "repo-skip",
				"platform_name": "missing-id",
				"platform_kind": "ecs",
			},
		},
	}

	lookup := GraphInfrastructurePlatformLookup{Graph: graph}
	result, err := lookup.ListProvisionedPlatforms(context.Background(), []string{"repo-infra", "repo-skip"})
	if err != nil {
		t.Fatalf("ListProvisionedPlatforms() error = %v", err)
	}

	if !strings.Contains(graph.cypher, "PROVISIONS_PLATFORM") {
		t.Fatalf("query missing PROVISIONS_PLATFORM: %s", graph.cypher)
	}
	if got, want := graph.params["repo_ids"].([]string), []string{"repo-infra", "repo-skip"}; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("repo_ids params = %v, want %v", got, want)
	}
	rows := result["repo-infra"]
	if len(rows) != 1 {
		t.Fatalf("len(result[repo-infra]) = %d, want 1", len(rows))
	}
	if got, want := rows[0].PlatformKind, "ecs"; got != want {
		t.Fatalf("PlatformKind = %q, want %q", got, want)
	}
	if got := len(result["repo-skip"]); got != 0 {
		t.Fatalf("len(result[repo-skip]) = %d, want 0 for incomplete platform row", got)
	}
}

type stubGraphQueryRunner struct {
	cypher string
	params map[string]any
	rows   []map[string]any
	err    error
}

func (f *stubGraphQueryRunner) Run(
	_ context.Context,
	cypher string,
	params map[string]any,
) ([]map[string]any, error) {
	f.cypher = cypher
	f.params = params
	if f.err != nil {
		return nil, f.err
	}
	return f.rows, nil
}
