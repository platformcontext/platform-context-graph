package pythonbridge

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

const gitCollectorBridgeModule = "platform_context_graph.runtime.ingester.go_collector_bridge"

// Source yields one compatibility-bridged collected generation at a time.
type Source interface {
	Next(context.Context) (CollectedGeneration, bool, error)
}

// Runner collects one batch of compatibility-bridged scope generations.
type Runner interface {
	Collect(context.Context) (Batch, error)
}

// Batch is one collector bridge response payload.
type Batch struct {
	Collected []CollectedGeneration
}

// CollectedGeneration is one repo-scoped source generation gathered by the
// Python compatibility bridge.
type CollectedGeneration struct {
	Scope      scope.IngestionScope
	Generation scope.ScopeGeneration
	Facts      []facts.Envelope
}

// BufferedSource drains one batch result one generation at a time.
type BufferedSource struct {
	Runner  Runner
	pending []CollectedGeneration
}

// Next returns one buffered generation, collecting a new batch when needed.
func (s *BufferedSource) Next(ctx context.Context) (CollectedGeneration, bool, error) {
	if len(s.pending) == 0 {
		if s.Runner == nil {
			return CollectedGeneration{}, false, fmt.Errorf("collector bridge runner is required")
		}
		batch, err := s.Runner.Collect(ctx)
		if err != nil {
			return CollectedGeneration{}, false, err
		}
		s.pending = append(s.pending, batch.Collected...)
	}
	if len(s.pending) == 0 {
		return CollectedGeneration{}, false, nil
	}

	item := s.pending[0]
	s.pending = s.pending[1:]
	return item, true, nil
}

// RunCommandFn executes the Python bridge command and returns stdout bytes.
type RunCommandFn func(
	ctx context.Context,
	name string,
	args []string,
	dir string,
	env []string,
) ([]byte, error)

// GitCollectorRunner executes the Python compatibility bridge for one sync
// cycle and decodes the emitted collected generations.
type GitCollectorRunner struct {
	PythonExecutable string
	RepoRoot         string
	Env              []string
	RunCommand       RunCommandFn
}

// Collect runs the Python bridge once and decodes the returned batch payload.
func (r GitCollectorRunner) Collect(ctx context.Context) (Batch, error) {
	repoRoot := strings.TrimSpace(r.RepoRoot)
	if repoRoot == "" {
		return Batch{}, fmt.Errorf("collector bridge repo root is required")
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
		[]string{"-m", gitCollectorBridgeModule},
		repoRoot,
		mergedEnv(r.Env, repoRoot),
	)
	if err != nil {
		return Batch{}, fmt.Errorf("run python collector bridge: %w", err)
	}

	batch, err := decodeCollectorBatch(stdout)
	if err != nil {
		return Batch{}, fmt.Errorf("decode collector bridge output: %w", err)
	}
	return batch, nil
}

func defaultRunCommand(
	ctx context.Context,
	name string,
	args []string,
	dir string,
	env []string,
) ([]byte, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = dir
	cmd.Env = append([]string(nil), env...)
	return cmd.Output()
}

func mergedEnv(base []string, repoRoot string) []string {
	env := append([]string(nil), base...)
	pythonPath := filepath.Join(repoRoot, "src")
	for i, entry := range env {
		if !strings.HasPrefix(entry, "PYTHONPATH=") {
			continue
		}

		existing := strings.TrimPrefix(entry, "PYTHONPATH=")
		if existing == "" {
			env[i] = "PYTHONPATH=" + pythonPath
			return env
		}
		env[i] = "PYTHONPATH=" + pythonPath + string(filepath.ListSeparator) + existing
		return env
	}

	return append(env, "PYTHONPATH="+pythonPath)
}

func decodeCollectorBatch(raw []byte) (Batch, error) {
	var payload batchJSON
	if err := json.Unmarshal(raw, &payload); err != nil {
		return Batch{}, err
	}

	collected := make([]CollectedGeneration, 0, len(payload.Collected))
	for i := range payload.Collected {
		generation, err := payload.Collected[i].toCollectedGeneration()
		if err != nil {
			return Batch{}, fmt.Errorf("collected[%d]: %w", i, err)
		}
		collected = append(collected, generation)
	}
	return Batch{Collected: collected}, nil
}

type batchJSON struct {
	Collected []collectedGenerationJSON `json:"collected"`
}

type collectedGenerationJSON struct {
	Scope      scopeJSON      `json:"scope"`
	Generation generationJSON `json:"generation"`
	Facts      []factJSON     `json:"facts"`
}

func (g collectedGenerationJSON) toCollectedGeneration() (CollectedGeneration, error) {
	scopeValue := g.Scope.toScope()
	if err := scopeValue.Validate(); err != nil {
		return CollectedGeneration{}, fmt.Errorf("scope: %w", err)
	}

	generationValue := g.Generation.toGeneration()
	if err := generationValue.ValidateForScope(scopeValue); err != nil {
		return CollectedGeneration{}, fmt.Errorf("generation: %w", err)
	}

	envelopes := make([]facts.Envelope, 0, len(g.Facts))
	for i := range g.Facts {
		envelopes = append(envelopes, g.Facts[i].toFact())
	}

	return CollectedGeneration{
		Scope:      scopeValue,
		Generation: generationValue,
		Facts:      envelopes,
	}, nil
}

type scopeJSON struct {
	ScopeID       string            `json:"scope_id"`
	SourceSystem  string            `json:"source_system"`
	ScopeKind     string            `json:"scope_kind"`
	ParentScopeID string            `json:"parent_scope_id"`
	CollectorKind string            `json:"collector_kind"`
	PartitionKey  string            `json:"partition_key"`
	Metadata      map[string]string `json:"metadata"`
}

func (s scopeJSON) toScope() scope.IngestionScope {
	return scope.IngestionScope{
		ScopeID:       s.ScopeID,
		SourceSystem:  s.SourceSystem,
		ScopeKind:     scope.ScopeKind(s.ScopeKind),
		ParentScopeID: s.ParentScopeID,
		CollectorKind: scope.CollectorKind(s.CollectorKind),
		PartitionKey:  s.PartitionKey,
		Metadata:      cloneStringMap(s.Metadata),
	}
}

type generationJSON struct {
	GenerationID  string    `json:"generation_id"`
	ScopeID       string    `json:"scope_id"`
	ObservedAt    time.Time `json:"observed_at"`
	IngestedAt    time.Time `json:"ingested_at"`
	Status        string    `json:"status"`
	TriggerKind   string    `json:"trigger_kind"`
	FreshnessHint string    `json:"freshness_hint"`
}

func (g generationJSON) toGeneration() scope.ScopeGeneration {
	return scope.ScopeGeneration{
		GenerationID:  g.GenerationID,
		ScopeID:       g.ScopeID,
		ObservedAt:    g.ObservedAt.UTC(),
		IngestedAt:    g.IngestedAt.UTC(),
		Status:        scope.GenerationStatus(g.Status),
		TriggerKind:   scope.TriggerKind(g.TriggerKind),
		FreshnessHint: g.FreshnessHint,
	}
}

type factJSON struct {
	FactID        string         `json:"fact_id"`
	ScopeID       string         `json:"scope_id"`
	GenerationID  string         `json:"generation_id"`
	FactKind      string         `json:"fact_kind"`
	StableFactKey string         `json:"stable_fact_key"`
	ObservedAt    time.Time      `json:"observed_at"`
	Payload       map[string]any `json:"payload"`
	IsTombstone   bool           `json:"is_tombstone"`
	SourceRef     factRefJSON    `json:"source_ref"`
}

func (f factJSON) toFact() facts.Envelope {
	return facts.Envelope{
		FactID:        f.FactID,
		ScopeID:       f.ScopeID,
		GenerationID:  f.GenerationID,
		FactKind:      f.FactKind,
		StableFactKey: f.StableFactKey,
		ObservedAt:    f.ObservedAt.UTC(),
		Payload:       cloneAnyMap(f.Payload),
		IsTombstone:   f.IsTombstone,
		SourceRef:     f.SourceRef.toRef(),
	}
}

type factRefJSON struct {
	SourceSystem   string `json:"source_system"`
	ScopeID        string `json:"scope_id"`
	GenerationID   string `json:"generation_id"`
	FactKey        string `json:"fact_key"`
	SourceURI      string `json:"source_uri"`
	SourceRecordID string `json:"source_record_id"`
}

func (r factRefJSON) toRef() facts.Ref {
	return facts.Ref{
		SourceSystem:   r.SourceSystem,
		ScopeID:        r.ScopeID,
		GenerationID:   r.GenerationID,
		FactKey:        r.FactKey,
		SourceURI:      r.SourceURI,
		SourceRecordID: r.SourceRecordID,
	}
}

func cloneStringMap(input map[string]string) map[string]string {
	if input == nil {
		return nil
	}

	cloned := make(map[string]string, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}

func cloneAnyMap(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}

	cloned := make(map[string]any, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}
