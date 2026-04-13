package pythonbridge

import (
	"context"
	"errors"
	"reflect"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

func TestDecodeCollectorBatchDecodesCollectedGenerations(t *testing.T) {
	t.Parallel()

	raw := []byte(`{
  "collected": [
    {
      "scope": {
        "scope_id": "scope-123",
        "source_system": "git",
        "scope_kind": "repository",
        "collector_kind": "git",
        "partition_key": "repository:r_123",
        "metadata": {
          "repo_id": "repository:r_123",
          "repo_name": "platform-context-graph"
        }
      },
      "generation": {
        "generation_id": "generation-456",
        "scope_id": "scope-123",
        "observed_at": "2026-04-12T12:00:00Z",
        "ingested_at": "2026-04-12T12:00:01Z",
        "status": "pending",
        "trigger_kind": "snapshot"
      },
      "facts": [
        {
          "fact_id": "fact-1",
          "scope_id": "scope-123",
          "generation_id": "generation-456",
          "fact_kind": "repository",
          "stable_fact_key": "repository:repository:r_123",
          "observed_at": "2026-04-12T12:00:00Z",
          "payload": {
            "graph_id": "repository:r_123",
            "graph_kind": "repository",
            "name": "platform-context-graph"
          },
          "source_ref": {
            "source_system": "git",
            "scope_id": "scope-123",
            "generation_id": "generation-456",
            "fact_key": "repository:r_123"
          }
        }
      ]
    }
  ]
}`)

	batch, err := decodeCollectorBatch(raw)
	if err != nil {
		t.Fatalf("decodeCollectorBatch() error = %v, want nil", err)
	}
	if got, want := len(batch.Collected), 1; got != want {
		t.Fatalf("len(batch.Collected) = %d, want %d", got, want)
	}

	collected := batch.Collected[0]
	if got, want := collected.Scope.ScopeID, "scope-123"; got != want {
		t.Fatalf("Scope.ScopeID = %q, want %q", got, want)
	}
	if got, want := collected.Generation.GenerationID, "generation-456"; got != want {
		t.Fatalf("Generation.GenerationID = %q, want %q", got, want)
	}
	if got, want := len(collected.Facts), 1; got != want {
		t.Fatalf("len(Facts) = %d, want %d", got, want)
	}
	if got, want := collected.Facts[0].SourceRef.FactKey, "repository:r_123"; got != want {
		t.Fatalf("Facts[0].SourceRef.FactKey = %q, want %q", got, want)
	}
}

func TestBufferedSourceReturnsBufferedResultsBeforeCollectingAgain(t *testing.T) {
	t.Parallel()

	first := CollectedGeneration{
		Scope:      testScope("scope-1"),
		Generation: testGeneration("scope-1", "generation-1"),
	}
	second := CollectedGeneration{
		Scope:      testScope("scope-2"),
		Generation: testGeneration("scope-2", "generation-2"),
	}
	runner := &stubRunner{
		batches: []Batch{
			{Collected: []CollectedGeneration{first, second}},
			{},
		},
	}
	source := &BufferedSource{Runner: runner}

	gotFirst, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next(first) error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next(first) ok = false, want true")
	}
	if !reflect.DeepEqual(gotFirst, first) {
		t.Fatalf("Next(first) = %#v, want %#v", gotFirst, first)
	}
	if got, want := runner.calls, 1; got != want {
		t.Fatalf("runner calls after first Next = %d, want %d", got, want)
	}

	gotSecond, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next(second) error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next(second) ok = false, want true")
	}
	if !reflect.DeepEqual(gotSecond, second) {
		t.Fatalf("Next(second) = %#v, want %#v", gotSecond, second)
	}
	if got, want := runner.calls, 1; got != want {
		t.Fatalf("runner calls after buffered Next = %d, want %d", got, want)
	}

	_, ok, err = source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next(empty) error = %v, want nil", err)
	}
	if ok {
		t.Fatal("Next(empty) ok = true, want false")
	}
	if got, want := runner.calls, 2; got != want {
		t.Fatalf("runner calls after empty batch = %d, want %d", got, want)
	}
}

func TestGitCollectorRunnerCollectRunsPythonBridgeCommand(t *testing.T) {
	t.Parallel()

	var gotName string
	var gotArgs []string
	var gotDir string
	var gotEnv []string

	runner := GitCollectorRunner{
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
			return []byte(`{"collected":[]}`), nil
		},
	}

	batch, err := runner.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect() error = %v, want nil", err)
	}
	if got, want := gotName, "python3"; got != want {
		t.Fatalf("command name = %q, want %q", got, want)
	}
	if got, want := gotDir, "/tmp/platform-context-graph"; got != want {
		t.Fatalf("command dir = %q, want %q", got, want)
	}
	wantArgs := []string{
		"-m",
		"platform_context_graph.runtime.ingester.go_collector_bridge",
	}
	if !reflect.DeepEqual(gotArgs, wantArgs) {
		t.Fatalf("command args = %v, want %v", gotArgs, wantArgs)
	}
	if len(gotEnv) == 0 {
		t.Fatal("command env = empty, want repo-root PYTHONPATH")
	}
	if got, want := len(batch.Collected), 0; got != want {
		t.Fatalf("len(batch.Collected) = %d, want %d", got, want)
	}
}

func TestGitCollectorRunnerCollectRejectsMissingRepoRoot(t *testing.T) {
	t.Parallel()

	runner := GitCollectorRunner{
		PythonExecutable: "python3",
		RunCommand: func(
			context.Context,
			string,
			[]string,
			string,
			[]string,
		) ([]byte, error) {
			return nil, errors.New("should not run")
		},
	}

	_, err := runner.Collect(context.Background())
	if err == nil {
		t.Fatal("Collect() error = nil, want non-nil")
	}
}

type stubRunner struct {
	batches []Batch
	calls   int
}

func (s *stubRunner) Collect(context.Context) (Batch, error) {
	if s.calls >= len(s.batches) {
		s.calls++
		return Batch{}, nil
	}

	batch := s.batches[s.calls]
	s.calls++
	return batch, nil
}

func testScope(scopeID string) scope.IngestionScope {
	return scope.IngestionScope{
		ScopeID:       scopeID,
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  scopeID,
	}
}

func testGeneration(scopeID string, generationID string) scope.ScopeGeneration {
	now := time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC)
	return scope.ScopeGeneration{
		GenerationID: generationID,
		ScopeID:      scopeID,
		ObservedAt:   now,
		IngestedAt:   now.Add(time.Second),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}
}
