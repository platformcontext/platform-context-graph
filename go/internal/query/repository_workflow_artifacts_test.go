package query

import (
	"context"
	"database/sql/driver"
	"testing"
)

func TestLoadRepositoryWorkflowArtifactsFallsBackToGetFileContent(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"repo_id", "relative_path", "commit_sha", "content",
				"content_hash", "line_count", "language", "artifact_type",
			},
			rows: [][]driver.Value{
				{
					"repo-1", ".github/workflows/deploy-gated.yml", "abc123", "",
					"hash-workflow", int64(16), "yaml", "github_actions_workflow",
				},
			},
		},
		{
			columns: []string{
				"repo_id", "relative_path", "commit_sha", "content",
				"content_hash", "line_count", "language", "artifact_type",
			},
			rows: [][]driver.Value{
				{
					"repo-1", ".github/workflows/deploy-gated.yml", "abc123", `name: deploy-gated

on:
  workflow_dispatch:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Verify worker
        run: echo "verifying service-worker-jobs"
  deploy:
    needs: verify
    if: ${{ github.ref == 'refs/heads/main' }}
    runs-on: ubuntu-latest
    steps:
      - name: Deploy gated worker
        if: ${{ inputs.deploy_enabled == 'true' }}
        run: echo "deploying gated service-worker-jobs"
`,
					"hash-workflow", int64(16), "yaml", "github_actions_workflow",
				},
			},
		},
	})

	reader := NewContentReader(db)
	got, err := loadRepositoryWorkflowArtifacts(
		context.Background(),
		reader,
		"repo-1",
		nil,
	)
	if err != nil {
		t.Fatalf("loadRepositoryWorkflowArtifacts() error = %v, want nil", err)
	}
	if got == nil {
		t.Fatal("loadRepositoryWorkflowArtifacts() = nil, want workflow_artifacts")
	}

	rows := mapSliceValue(got, "workflow_artifacts")
	if len(rows) != 1 {
		t.Fatalf("len(workflow_artifacts) = %d, want 1", len(rows))
	}

	row := rows[0]
	if got, want := row["workflow_name"], "deploy-gated"; got != want {
		t.Fatalf("workflow_artifacts[0].workflow_name = %#v, want %#v", got, want)
	}
	if got, want := row["command_count"], 2; got != want {
		t.Fatalf("workflow_artifacts[0].command_count = %#v, want %#v", got, want)
	}
	gatingConditions := StringSliceVal(row, "gating_conditions")
	if len(gatingConditions) != 2 {
		t.Fatalf("len(workflow_artifacts[0].gating_conditions) = %d, want 2", len(gatingConditions))
	}
	if gatingConditions[0] != "job deploy if ${{ github.ref == 'refs/heads/main' }}" {
		t.Fatalf("workflow_artifacts[0].gating_conditions[0] = %q, want job condition", gatingConditions[0])
	}
	needsDependencies := StringSliceVal(row, "needs_dependencies")
	if len(needsDependencies) != 1 || needsDependencies[0] != "deploy<-verify" {
		t.Fatalf("workflow_artifacts[0].needs_dependencies = %#v, want [deploy<-verify]", needsDependencies)
	}
}
