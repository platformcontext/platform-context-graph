package projector

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

func TestRuntimeProjectDefaultWritesCanonicalBeforeContent(t *testing.T) {
	t.Parallel()

	var order []string
	runtime := Runtime{
		CanonicalWriter: &orderedCanonicalWriter{order: &order},
		ContentWriter:   &orderedContentWriter{order: &order, result: content.Result{RecordCount: 1}},
	}

	_, err := runtime.Project(context.Background(), orderScope(), orderGeneration(), orderFacts())
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}
	assertOrder(t, order, []string{"canonical", "content"})
}

func TestRuntimeProjectContentBeforeCanonicalWritesContentFirst(t *testing.T) {
	t.Parallel()

	var order []string
	runtime := Runtime{
		CanonicalWriter:        &orderedCanonicalWriter{order: &order},
		ContentWriter:          &orderedContentWriter{order: &order, result: content.Result{RecordCount: 1}},
		ContentBeforeCanonical: true,
	}

	_, err := runtime.Project(context.Background(), orderScope(), orderGeneration(), orderFacts())
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}
	assertOrder(t, order, []string{"content", "canonical"})
}

func TestRuntimeProjectContentBeforeCanonicalKeepsContentWhenCanonicalFails(t *testing.T) {
	t.Parallel()

	var order []string
	expectedErr := errors.New("graph backend timed out")
	runtime := Runtime{
		CanonicalWriter:        &orderedCanonicalWriter{order: &order, err: expectedErr},
		ContentWriter:          &orderedContentWriter{order: &order, result: content.Result{RecordCount: 1}},
		ContentBeforeCanonical: true,
	}

	_, err := runtime.Project(context.Background(), orderScope(), orderGeneration(), orderFacts())
	if !errors.Is(err, expectedErr) {
		t.Fatalf("Project() error = %v, want %v", err, expectedErr)
	}
	assertOrder(t, order, []string{"content", "canonical"})
}

func TestRuntimeProjectEnqueuesReducerIntentsBeforeContentWrite(t *testing.T) {
	t.Parallel()

	var order []string
	runtime := Runtime{
		CanonicalWriter: &orderedCanonicalWriter{order: &order},
		ContentWriter:   &orderedContentWriter{order: &order, result: content.Result{RecordCount: 1}},
		IntentWriter:    &orderedIntentWriter{order: &order, result: IntentResult{Count: 1}},
	}

	result, err := runtime.Project(context.Background(), orderScope(), orderGeneration(), orderFactsWithIntent())
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}
	if got, want := result.Intents.Count, 1; got != want {
		t.Fatalf("result.Intents.Count = %d, want %d", got, want)
	}
	assertOrder(t, order, []string{"canonical", "intent", "content"})
}

func orderScope() scope.IngestionScope {
	return scope.IngestionScope{
		ScopeID:       "scope-order",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-order",
		Metadata: map[string]string{
			"repo_id": "repository:r_order",
		},
	}
}

func orderGeneration() scope.ScopeGeneration {
	return scope.ScopeGeneration{
		GenerationID: "generation-order",
		ScopeID:      "scope-order",
		ObservedAt:   time.Date(2026, time.April, 22, 10, 0, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 22, 10, 1, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}
}

func orderFacts() []facts.Envelope {
	observedAt := time.Date(2026, time.April, 22, 10, 0, 0, 0, time.UTC)
	return []facts.Envelope{
		{
			FactID:       "fact-repo",
			ScopeID:      "scope-order",
			GenerationID: "generation-order",
			FactKind:     "repository",
			ObservedAt:   observedAt,
			Payload: map[string]any{
				"repo_id": "repository:r_order",
				"name":    "platform-context-graph",
				"path":    "/workspace/platform-context-graph",
			},
		},
		{
			FactID:       "fact-content",
			ScopeID:      "scope-order",
			GenerationID: "generation-order",
			FactKind:     "source_content",
			ObservedAt:   observedAt,
			Payload: map[string]any{
				"content_path":   "README.md",
				"content_body":   "# Platform Context Graph",
				"content_digest": "digest-order",
			},
		},
	}
}

func orderFactsWithIntent() []facts.Envelope {
	envelopes := orderFacts()
	envelopes = append(envelopes, facts.Envelope{
		FactID:       "fact-reducer-intent",
		ScopeID:      "scope-order",
		GenerationID: "generation-order",
		FactKind:     "source_relation",
		ObservedAt:   time.Date(2026, time.April, 22, 10, 0, 0, 0, time.UTC),
		Payload: map[string]any{
			"reducer_domain": string(reducer.DomainCodeCallMaterialization),
			"entity_key":     "repository:r_order",
			"reason":         "code-call follow-up required",
		},
	})
	return envelopes
}

type orderedCanonicalWriter struct {
	order *[]string
	err   error
}

func (w *orderedCanonicalWriter) Write(_ context.Context, _ CanonicalMaterialization) error {
	*w.order = append(*w.order, "canonical")
	return w.err
}

type orderedContentWriter struct {
	order  *[]string
	result content.Result
}

func (w *orderedContentWriter) Write(_ context.Context, materialization content.Materialization) (content.Result, error) {
	*w.order = append(*w.order, "content")
	if len(materialization.Records) == 0 {
		return content.Result{}, errors.New("content materialization is empty")
	}
	return w.result, nil
}

type orderedIntentWriter struct {
	order  *[]string
	result IntentResult
}

func (w *orderedIntentWriter) Enqueue(_ context.Context, _ []ReducerIntent) (IntentResult, error) {
	*w.order = append(*w.order, "intent")
	return w.result, nil
}

func assertOrder(t *testing.T, got []string, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("order = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("order = %v, want %v", got, want)
		}
	}
}
