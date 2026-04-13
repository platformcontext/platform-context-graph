package pythonbridge

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
)

const gitCollectorSnapshotBridgeModule = "platform_context_graph.runtime.ingester.go_collector_snapshot_bridge"

// GitRepositorySnapshotRunner executes the narrowed Python snapshot bridge for
// one selected repository.
type GitRepositorySnapshotRunner struct {
	PythonExecutable string
	RepoRoot         string
	Env              []string
	RunCommand       RunCommandFn
}

// SnapshotRepository runs the Python snapshot bridge once for one repository
// and decodes the snapshot payload.
func (r GitRepositorySnapshotRunner) SnapshotRepository(
	ctx context.Context,
	repository collector.SelectedRepository,
) (collector.RepositorySnapshot, error) {
	repoRoot := strings.TrimSpace(r.RepoRoot)
	if repoRoot == "" {
		return collector.RepositorySnapshot{}, fmt.Errorf("collector snapshot bridge repo root is required")
	}
	repositoryPath := strings.TrimSpace(repository.RepoPath)
	if repositoryPath == "" {
		return collector.RepositorySnapshot{}, fmt.Errorf("selected repository repo_path is required")
	}

	pythonExecutable := strings.TrimSpace(r.PythonExecutable)
	if pythonExecutable == "" {
		pythonExecutable = "python3"
	}

	runCommand := r.RunCommand
	if runCommand == nil {
		runCommand = defaultRunCommand
	}

	stdout, err := runCommand(
		ctx,
		pythonExecutable,
		[]string{
			"-m",
			gitCollectorSnapshotBridgeModule,
			"--repo-path",
			repositoryPath,
		},
		repoRoot,
		mergedEnv(r.Env, repoRoot),
	)
	if err != nil {
		return collector.RepositorySnapshot{}, fmt.Errorf("run python collector snapshot bridge: %w", err)
	}

	snapshot, err := decodeSnapshot(stdout)
	if err != nil {
		return collector.RepositorySnapshot{}, fmt.Errorf("decode collector snapshot bridge output: %w", err)
	}
	if strings.TrimSpace(snapshot.RepoPath) == "" {
		snapshot.RepoPath = repositoryPath
	}
	if strings.TrimSpace(snapshot.RemoteURL) == "" {
		snapshot.RemoteURL = repository.RemoteURL
	}
	return snapshot, nil
}

func decodeSnapshot(raw []byte) (collector.RepositorySnapshot, error) {
	var payload collector.RepositorySnapshot
	if err := json.Unmarshal(raw, &payload); err != nil {
		return collector.RepositorySnapshot{}, err
	}
	return payload, nil
}
