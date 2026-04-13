package pythonbridge

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
)

const gitCollectorSelectionBridgeModule = "platform_context_graph.runtime.ingester.go_collector_selection_bridge"

// GitSelectionRunner executes the narrowed Python selection bridge for one
// sync cycle.
type GitSelectionRunner struct {
	PythonExecutable string
	RepoRoot         string
	Env              []string
	RunCommand       RunCommandFn
}

// SelectRepositories runs the Python selection bridge once and decodes the
// repository batch payload.
func (r GitSelectionRunner) SelectRepositories(
	ctx context.Context,
) (collector.SelectionBatch, error) {
	repoRoot := strings.TrimSpace(r.RepoRoot)
	if repoRoot == "" {
		return collector.SelectionBatch{}, fmt.Errorf("collector selection bridge repo root is required")
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
		[]string{"-m", gitCollectorSelectionBridgeModule},
		repoRoot,
		mergedEnv(r.Env, repoRoot),
	)
	if err != nil {
		return collector.SelectionBatch{}, fmt.Errorf("run python collector selection bridge: %w", err)
	}

	batch, err := decodeSelectionBatch(stdout)
	if err != nil {
		return collector.SelectionBatch{}, fmt.Errorf("decode collector selection bridge output: %w", err)
	}
	return batch, nil
}

func decodeSelectionBatch(raw []byte) (collector.SelectionBatch, error) {
	var payload selectionBatchJSON
	if err := json.Unmarshal(raw, &payload); err != nil {
		return collector.SelectionBatch{}, err
	}

	repositories := make([]collector.SelectedRepository, 0, len(payload.Repositories))
	for _, repository := range payload.Repositories {
		repositories = append(
			repositories,
			collector.SelectedRepository{
				RepoPath:  repository.RepoPath,
				RemoteURL: repository.remoteURL(),
			},
		)
	}

	return collector.SelectionBatch{
		ObservedAt:   payload.ObservedAt.UTC(),
		Repositories: repositories,
	}, nil
}

type selectionBatchJSON struct {
	ObservedAt   time.Time                `json:"observed_at"`
	Repositories []selectedRepositoryJSON `json:"repositories"`
}

type selectedRepositoryJSON struct {
	RepoPath  string  `json:"repo_path"`
	RemoteURL *string `json:"remote_url"`
}

func (r selectedRepositoryJSON) remoteURL() string {
	if r.RemoteURL == nil {
		return ""
	}
	return strings.TrimSpace(*r.RemoteURL)
}
