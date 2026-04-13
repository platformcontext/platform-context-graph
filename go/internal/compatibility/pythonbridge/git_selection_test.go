package pythonbridge

import (
	"context"
	"testing"
	"time"
)

func TestGitSelectionRunnerSelectRepositoriesRunsPythonSelectionBridge(t *testing.T) {
	t.Parallel()

	var gotName string
	var gotArgs []string
	var gotDir string
	var gotEnv []string

	runner := GitSelectionRunner{
		PythonExecutable: "python3",
		RepoRoot:         "/tmp/platform-context-graph",
		Env:              []string{"PATH=/usr/bin", "PYTHONPATH=/existing"},
		RunCommand: func(
			_ context.Context,
			name string,
			args []string,
			dir string,
			env []string,
		) ([]byte, error) {
			gotName = name
			gotArgs = append([]string(nil), args...)
			gotDir = dir
			gotEnv = append([]string(nil), env...)
			return []byte(`{
  "observed_at":"2026-04-12T15:30:00Z",
  "repositories":[
    {
      "repo_path":"/tmp/service",
      "remote_url":"https://github.com/example/service"
    }
  ]
}`), nil
		},
	}

	batch, err := runner.SelectRepositories(context.Background())
	if err != nil {
		t.Fatalf("SelectRepositories() error = %v, want nil", err)
	}
	if got, want := gotName, "python3"; got != want {
		t.Fatalf("command name = %q, want %q", got, want)
	}
	if got, want := gotDir, "/tmp/platform-context-graph"; got != want {
		t.Fatalf("command dir = %q, want %q", got, want)
	}
	wantArgs := []string{
		"-m",
		"platform_context_graph.runtime.ingester.go_collector_selection_bridge",
	}
	if len(gotArgs) != len(wantArgs) {
		t.Fatalf("len(command args) = %d, want %d", len(gotArgs), len(wantArgs))
	}
	for i, want := range wantArgs {
		if got := gotArgs[i]; got != want {
			t.Fatalf("command args[%d] = %q, want %q", i, got, want)
		}
	}
	if len(gotEnv) == 0 {
		t.Fatal("command env = empty, want repo-root PYTHONPATH")
	}
	if got, want := batch.ObservedAt, time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC); !got.Equal(want) {
		t.Fatalf("ObservedAt = %v, want %v", got, want)
	}
	if got, want := len(batch.Repositories), 1; got != want {
		t.Fatalf("len(Repositories) = %d, want %d", got, want)
	}
	if got, want := batch.Repositories[0].RepoPath, "/tmp/service"; got != want {
		t.Fatalf("RepoPath = %q, want %q", got, want)
	}
}
