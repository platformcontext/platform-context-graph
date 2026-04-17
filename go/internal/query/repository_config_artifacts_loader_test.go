package query

import (
	"context"
	"database/sql/driver"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestLoadRepositoryControllerArtifactsFallsBackToGetFileContentForJenkinsfile(t *testing.T) {
	t.Parallel()

	fixtureContent := readAnsibleJenkinsAutomationFixture(t, "Jenkinsfile")
	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"repo_id", "relative_path", "commit_sha", "content",
				"content_hash", "line_count", "language", "artifact_type",
			},
			rows: [][]driver.Value{
				{
					"repo-1", "Jenkinsfile", "abc123", fixtureContent,
					"hash-jenkins", int64(12), "groovy", "groovy",
				},
			},
		},
	})

	reader := NewContentReader(db)
	got, err := loadRepositoryControllerArtifacts(
		context.Background(),
		reader,
		"repo-1",
		"controller-service",
		[]FileContent{{RelativePath: "Jenkinsfile"}},
	)
	if err != nil {
		t.Fatalf("loadRepositoryControllerArtifacts() error = %v, want nil", err)
	}
	if got == nil {
		t.Fatal("loadRepositoryControllerArtifacts() = nil, want controller_artifacts")
	}

	artifacts := mapSliceValue(got, "controller_artifacts")
	if len(artifacts) != 1 {
		t.Fatalf("len(controller_artifacts) = %d, want 1", len(artifacts))
	}

	row := artifacts[0]
	if got, want := row["path"], "Jenkinsfile"; got != want {
		t.Fatalf("controller_artifacts[0].path = %#v, want %#v", got, want)
	}
	if got, want := row["controller_kind"], "jenkins_pipeline"; got != want {
		t.Fatalf("controller_artifacts[0].controller_kind = %#v, want %#v", got, want)
	}

	pipelineCalls := StringSliceVal(row, "pipeline_calls")
	if len(pipelineCalls) != 1 || pipelineCalls[0] != "pipelineDeploy" {
		t.Fatalf("controller_artifacts[0].pipeline_calls = %#v, want [pipelineDeploy]", row["pipeline_calls"])
	}
	shellCommands := StringSliceVal(row, "shell_commands")
	if len(shellCommands) != 1 || shellCommands[0] != "./scripts/deploy.sh" {
		t.Fatalf("controller_artifacts[0].shell_commands = %#v, want [./scripts/deploy.sh]", row["shell_commands"])
	}
}

func readAnsibleJenkinsAutomationFixture(t *testing.T, parts ...string) string {
	t.Helper()

	path := ansibleJenkinsAutomationFixturePath(parts...)
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("os.ReadFile(%q) error = %v, want nil", path, err)
	}
	return string(body)
}

func ansibleJenkinsAutomationFixturePath(parts ...string) string {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		return ""
	}

	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "tests", "fixtures", "ecosystems", "ansible_jenkins_automation"))
	elems := append([]string{root}, parts...)
	return filepath.Join(elems...)
}
