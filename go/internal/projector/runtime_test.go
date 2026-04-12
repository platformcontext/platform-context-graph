package projector

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestRuntimeProjectMaterializesSourceLocalTruthAndReducerIntents(t *testing.T) {
	t.Parallel()

	graphWriter := &recordingGraphWriter{result: graph.Result{RecordCount: 1}}
	contentWriter := &recordingContentWriter{result: content.Result{RecordCount: 1}}
	intentWriter := &recordingIntentWriter{result: IntentResult{Count: 1}}

	runtime := Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: contentWriter,
		IntentWriter:  intentWriter,
	}

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
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}

	result, err := runtime.Project(context.Background(), scopeValue, generationValue, []facts.Envelope{
		{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_node",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
			Payload: map[string]any{
				"graph_id":   "repo-123",
				"graph_kind": "repository",
				"name":       "platform-context-graph",
			},
		},
		{
			FactID:       "fact-2",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_content",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 32, 0, 0, time.UTC),
			Payload: map[string]any{
				"content_path":   "README.md",
				"content_body":   "# PCG",
				"content_digest": "digest-1",
			},
		},
		{
			FactID:       "fact-3",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_relation",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 33, 0, 0, time.UTC),
			Payload: map[string]any{
				"reducer_domain": "workload_identity",
				"entity_key":     "repo-123",
				"reason":         "shared identity follow-up required",
			},
		},
	})
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}

	if got, want := result.ScopeGenerationKey(), "scope-123:generation-456"; got != want {
		t.Fatalf("Result.ScopeGenerationKey() = %q, want %q", got, want)
	}
	if got, want := runtime.TraceSpanName(), telemetry.SpanProjectorRun; got != want {
		t.Fatalf("TraceSpanName() = %q, want %q", got, want)
	}
	if got, want := graphWriter.calls[0].ScopeGenerationKey(), "scope-123:generation-456"; got != want {
		t.Fatalf("graph write scope-generation key = %q, want %q", got, want)
	}
	if got, want := contentWriter.calls[0].ScopeGenerationKey(), "scope-123:generation-456"; got != want {
		t.Fatalf("content write scope-generation key = %q, want %q", got, want)
	}
	if got, want := intentWriter.calls[0][0].ScopeGenerationKey(), "scope-123:generation-456"; got != want {
		t.Fatalf("intent scope-generation key = %q, want %q", got, want)
	}
	if got, want := result.Graph.RecordCount, 1; got != want {
		t.Fatalf("result.Graph.RecordCount = %d, want %d", got, want)
	}
	if got, want := result.Content.RecordCount, 1; got != want {
		t.Fatalf("result.Content.RecordCount = %d, want %d", got, want)
	}
	if got, want := result.Intents.Count, 1; got != want {
		t.Fatalf("result.Intents.Count = %d, want %d", got, want)
	}
}

func TestRuntimeProjectRejectsCrossGenerationFacts(t *testing.T) {
	t.Parallel()

	runtime := Runtime{}
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
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}

	_, err := runtime.Project(context.Background(), scopeValue, generationValue, []facts.Envelope{{
		FactID:       "fact-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-999",
		FactKind:     "source_node",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
	}})
	if err == nil {
		t.Fatal("Project() error = nil, want non-nil")
	}
}

func TestRuntimeProjectCopiesRepoIDIntoContentMaterialization(t *testing.T) {
	t.Parallel()

	contentWriter := &recordingContentWriter{result: content.Result{RecordCount: 1}}
	runtime := Runtime{
		ContentWriter: contentWriter,
	}

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
		Metadata: map[string]string{
			"repo_id": "repository:r_12345678",
		},
	}
	generationValue := scope.ScopeGeneration{
		GenerationID: "generation-456",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}

	_, err := runtime.Project(context.Background(), scopeValue, generationValue, []facts.Envelope{
		{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_content",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 32, 0, 0, time.UTC),
			Payload: map[string]any{
				"content_path":   "README.md",
				"content_body":   "# PCG",
				"content_digest": "digest-1",
			},
		},
	})
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}
	if got, want := len(contentWriter.calls), 1; got != want {
		t.Fatalf("content writer call count = %d, want %d", got, want)
	}
	if got, want := contentWriter.calls[0].RepoID, "repository:r_12345678"; got != want {
		t.Fatalf("content materialization repo id = %q, want %q", got, want)
	}
}

func TestRuntimeProjectMaterializesExplicitEntityRecords(t *testing.T) {
	t.Parallel()

	contentWriter := &recordingContentWriter{result: content.Result{EntityCount: 1}}
	runtime := Runtime{
		ContentWriter: contentWriter,
	}

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
		Metadata: map[string]string{
			"repo_id": "repository:r_12345678",
		},
	}
	generationValue := scope.ScopeGeneration{
		GenerationID: "generation-456",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}

	result, err := runtime.Project(context.Background(), scopeValue, generationValue, []facts.Envelope{
		{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "content_entity",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 32, 0, 0, time.UTC),
			Payload: map[string]any{
				"content_path": "schema.sql",
				"entity_type":  "SqlTable",
				"entity_name":  "public.users",
				"start_line":   10,
				"end_line":     20,
				"language":     "sql",
				"source_cache": "create table public.users",
			},
		},
	})
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}
	if got, want := len(contentWriter.calls), 1; got != want {
		t.Fatalf("content writer call count = %d, want %d", got, want)
	}
	if got, want := len(contentWriter.calls[0].Records), 0; got != want {
		t.Fatalf("content record count = %d, want %d", got, want)
	}
	if got, want := len(contentWriter.calls[0].Entities), 1; got != want {
		t.Fatalf("content entity count = %d, want %d", got, want)
	}
	if got, want := result.Content.EntityCount, 1; got != want {
		t.Fatalf("result.Content.EntityCount = %d, want %d", got, want)
	}

	entity := contentWriter.calls[0].Entities[0]
	if got, want := entity.EntityID, content.CanonicalEntityID(
		"repository:r_12345678",
		"schema.sql",
		"SqlTable",
		"public.users",
		10,
	); got != want {
		t.Fatalf("content entity id = %q, want %q", got, want)
	}
	if got, want := entity.Path, "schema.sql"; got != want {
		t.Fatalf("content entity path = %q, want %q", got, want)
	}
	if got, want := entity.EntityType, "SqlTable"; got != want {
		t.Fatalf("content entity type = %q, want %q", got, want)
	}
	if got, want := entity.EntityName, "public.users"; got != want {
		t.Fatalf("content entity name = %q, want %q", got, want)
	}
	if got, want := entity.StartLine, 10; got != want {
		t.Fatalf("content entity start line = %d, want %d", got, want)
	}
	if got, want := entity.EndLine, 20; got != want {
		t.Fatalf("content entity end line = %d, want %d", got, want)
	}
	if got, want := entity.SourceCache, "create table public.users"; got != want {
		t.Fatalf("content entity source cache = %q, want %q", got, want)
	}
}

type recordingGraphWriter struct {
	calls  []graph.Materialization
	result graph.Result
}

func (w *recordingGraphWriter) Write(_ context.Context, materialization graph.Materialization) (graph.Result, error) {
	w.calls = append(w.calls, materialization.Clone())
	return w.result, nil
}

type recordingContentWriter struct {
	calls  []content.Materialization
	result content.Result
}

func (w *recordingContentWriter) Write(_ context.Context, materialization content.Materialization) (content.Result, error) {
	w.calls = append(w.calls, materialization.Clone())
	return w.result, nil
}

type recordingIntentWriter struct {
	calls  [][]ReducerIntent
	result IntentResult
}

func (w *recordingIntentWriter) Enqueue(_ context.Context, intents []ReducerIntent) (IntentResult, error) {
	cloned := make([]ReducerIntent, len(intents))
	copy(cloned, intents)
	w.calls = append(w.calls, cloned)
	return w.result, nil
}
