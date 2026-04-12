package pythonbridge

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
)

const gitCollectorSnapshotBridgeModule = "platform_context_graph.runtime.ingester.go_collector_snapshot_bridge"

// GitSnapshotRunner executes the narrowed Python snapshot bridge for one sync cycle.
type GitSnapshotRunner struct {
	PythonExecutable string
	RepoRoot         string
	Env              []string
	RunCommand       RunCommandFn
}

// CollectSnapshots runs the Python snapshot bridge once and decodes the batch payload.
func (r GitSnapshotRunner) CollectSnapshots(ctx context.Context) (collector.SnapshotBatch, error) {
	repoRoot := strings.TrimSpace(r.RepoRoot)
	if repoRoot == "" {
		return collector.SnapshotBatch{}, fmt.Errorf("collector snapshot bridge repo root is required")
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
		[]string{"-m", gitCollectorSnapshotBridgeModule},
		repoRoot,
		mergedEnv(r.Env, repoRoot),
	)
	if err != nil {
		return collector.SnapshotBatch{}, fmt.Errorf("run python collector snapshot bridge: %w", err)
	}

	batch, err := decodeSnapshotBatch(stdout)
	if err != nil {
		return collector.SnapshotBatch{}, fmt.Errorf("decode collector snapshot bridge output: %w", err)
	}
	return batch, nil
}

func decodeSnapshotBatch(raw []byte) (collector.SnapshotBatch, error) {
	var payload snapshotBatchJSON
	if err := json.Unmarshal(raw, &payload); err != nil {
		return collector.SnapshotBatch{}, err
	}

	return collector.SnapshotBatch{
		ObservedAt:   payload.ObservedAt.UTC(),
		Repositories: payload.Collected,
	}, nil
}

type snapshotBatchJSON struct {
	ObservedAt time.Time                      `json:"observed_at"`
	Collected  []collector.RepositorySnapshot `json:"collected"`
}
