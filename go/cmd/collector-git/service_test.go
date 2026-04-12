package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	pythonbridge "github.com/platformcontext/platform-context-graph/go/internal/compatibility/pythonbridge"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestServiceRunCommitsCollectedGenerationViaDurableBoundary(t *testing.T) {
	t.Parallel()

	scopeValue, generationValue, envelopes := testCollectedGeneration()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	source := &stubSource{
		collected: []collectedGeneration{{
			Scope:      scopeValue,
			Generation: generationValue,
			Facts:      envelopes,
		}},
	}
	committer := &stubCommitter{
		commit: func(_ context.Context, gotScope scope.IngestionScope, gotGeneration scope.ScopeGeneration, gotFacts []facts.Envelope) error {
			cancel()

			if !reflect.DeepEqual(gotScope, scopeValue) {
				t.Fatalf("CommitScopeGeneration() scope = %#v, want %#v", gotScope, scopeValue)
			}
			if gotGeneration != generationValue {
				t.Fatalf("CommitScopeGeneration() generation = %#v, want %#v", gotGeneration, generationValue)
			}
			if len(gotFacts) != len(envelopes) {
				t.Fatalf("CommitScopeGeneration() fact count = %d, want %d", len(gotFacts), len(envelopes))
			}

			return nil
		},
	}

	service := Service{
		Source:       source,
		Committer:    committer,
		PollInterval: time.Millisecond,
	}

	if err := service.Run(ctx); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}
	if got, want := committer.calls, 1; got != want {
		t.Fatalf("CommitScopeGeneration() call count = %d, want %d", got, want)
	}
}

func TestServiceRunPropagatesDurableCommitErrors(t *testing.T) {
	t.Parallel()

	scopeValue, generationValue, envelopes := testCollectedGeneration()
	wantErr := errors.New("commit failed")

	service := Service{
		Source: &stubSource{
			collected: []collectedGeneration{{
				Scope:      scopeValue,
				Generation: generationValue,
				Facts:      envelopes,
			}},
		},
		Committer: &stubCommitter{
			commit: func(context.Context, scope.IngestionScope, scope.ScopeGeneration, []facts.Envelope) error {
				return wantErr
			},
		},
		PollInterval: time.Millisecond,
	}

	err := service.Run(context.Background())
	if !errors.Is(err, wantErr) {
		t.Fatalf("Run() error = %v, want wrapped %v", err, wantErr)
	}
}

func TestBuildCollectorServiceUsesIngestionStoreBoundary(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	srcDir := filepath.Join(repoRoot, "src", "platform_context_graph")
	if err := os.MkdirAll(srcDir, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", srcDir, err)
	}

	service, err := buildCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return repoRoot, nil },
		func() []string { return []string{"PATH=/usr/bin"} },
	)
	if err != nil {
		t.Fatalf("buildCollectorService() error = %v, want nil", err)
	}
	if service.Source == nil {
		t.Fatal("buildCollectorService() source = nil, want non-nil")
	}
	if _, ok := service.Source.(*pythonbridge.BufferedSource); !ok {
		t.Fatalf("buildCollectorService() source type = %T, want *pythonbridge.BufferedSource", service.Source)
	}
	if service.PollInterval <= 0 {
		t.Fatalf("buildCollectorService() poll interval = %v, want positive", service.PollInterval)
	}
	if _, ok := service.Committer.(postgres.IngestionStore); !ok {
		t.Fatalf("buildCollectorService() committer type = %T, want postgres.IngestionStore", service.Committer)
	}
}

func TestBuildCollectorServiceRejectsMissingBridgeRepoRoot(t *testing.T) {
	t.Parallel()

	_, err := buildCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return "/tmp/does-not-exist", nil },
		func() []string { return nil },
	)
	if err == nil {
		t.Fatal("buildCollectorService() error = nil, want non-nil")
	}
}

func testCollectedGeneration() (scope.IngestionScope, scope.ScopeGeneration, []facts.Envelope) {
	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
	}
	generationValue := scope.ScopeGeneration{
		GenerationID: "generation-456",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 12, 1, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}
	envelopes := []facts.Envelope{{
		FactID:        "fact-1",
		ScopeID:       "scope-123",
		GenerationID:  "generation-456",
		FactKind:      "repository",
		StableFactKey: "repository:repo-123",
		ObservedAt:    generationValue.ObservedAt,
		Payload:       map[string]any{"graph_id": "repo-123"},
		SourceRef: facts.Ref{
			SourceSystem: "git",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKey:      "fact-key",
		},
	}}

	return scopeValue, generationValue, envelopes
}

type stubSource struct {
	collected []collectedGeneration
	index     int
}

func (s *stubSource) Next(ctx context.Context) (collectedGeneration, bool, error) {
	if s.index >= len(s.collected) {
		<-ctx.Done()
		return collectedGeneration{}, false, ctx.Err()
	}

	item := s.collected[s.index]
	s.index++
	return item, true, nil
}

type stubCommitter struct {
	calls  int
	commit func(context.Context, scope.IngestionScope, scope.ScopeGeneration, []facts.Envelope) error
}

func (s *stubCommitter) CommitScopeGeneration(
	ctx context.Context,
	scopeValue scope.IngestionScope,
	generationValue scope.ScopeGeneration,
	envelopes []facts.Envelope,
) error {
	s.calls++
	if s.commit != nil {
		return s.commit(ctx, scopeValue, generationValue, envelopes)
	}

	return nil
}
