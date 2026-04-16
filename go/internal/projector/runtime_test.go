package projector

import (
	"context"
	"testing"
	"time"

	metricnoop "go.opentelemetry.io/otel/metric/noop"
	"go.opentelemetry.io/otel/trace/noop"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestRuntimeProjectMaterializesSourceLocalTruthAndReducerIntents(t *testing.T) {
	t.Parallel()

	canonicalWriter := &recordingCanonicalWriter{}
	contentWriter := &recordingContentWriter{result: content.Result{RecordCount: 1}}
	intentWriter := &recordingIntentWriter{result: IntentResult{Count: 1}}

	runtime := Runtime{
		CanonicalWriter: canonicalWriter,
		ContentWriter:   contentWriter,
		IntentWriter:    intentWriter,
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
			FactID:       "fact-0",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "repository",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
			Payload: map[string]any{
				"repo_id": "repo-123",
				"name":    "platform-context-graph",
				"path":    "org/platform-context-graph",
			},
		},
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
	if got, want := len(canonicalWriter.calls), 1; got < want {
		t.Fatalf("canonical writer call count = %d, want >= %d", got, want)
	}
	if got, want := contentWriter.calls[0].ScopeGenerationKey(), "scope-123:generation-456"; got != want {
		t.Fatalf("content write scope-generation key = %q, want %q", got, want)
	}
	if got, want := intentWriter.calls[0][0].ScopeGenerationKey(), "scope-123:generation-456"; got != want {
		t.Fatalf("intent scope-generation key = %q, want %q", got, want)
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

func TestBuildReducerIntentRejectsUnknownDomain(t *testing.T) {
	t.Parallel()

	_, ok := buildReducerIntent(facts.Envelope{
		FactID:       "fact-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		Payload: map[string]any{
			"reducer_domain": "not_a_real_domain",
		},
	})
	if ok {
		t.Fatal("buildReducerIntent() ok = true, want false")
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
				"entity_metadata": map[string]any{
					"docstring":  "Primary table.",
					"decorators": []string{"@tracked"},
				},
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
	if got, want := entity.Metadata["docstring"], "Primary table."; got != want {
		t.Fatalf("content entity metadata docstring = %#v, want %#v", got, want)
	}
}

func TestRuntimeProjectEnqueuesSemanticEntityMaterializationForAnnotationTypedefTypeAliasComponentAndFunction(t *testing.T) {
	t.Parallel()

	contentWriter := &recordingContentWriter{result: content.Result{EntityCount: 2}}
	intentWriter := &recordingIntentWriter{result: IntentResult{Count: 5}}
	runtime := Runtime{
		ContentWriter: contentWriter,
		IntentWriter:  intentWriter,
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
			SourceRef: facts.Ref{
				SourceSystem: "git",
			},
			Payload: map[string]any{
				"entity_id":     "annotation-1",
				"entity_type":   "Annotation",
				"entity_name":   "Logged",
				"relative_path": "src/Logged.java",
				"repo_id":       "repository:r_12345678",
				"language":      "java",
			},
		},
		{
			FactID:       "fact-2",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "content_entity",
			SourceRef: facts.Ref{
				SourceSystem: "git",
			},
			Payload: map[string]any{
				"entity_id":     "typedef-1",
				"entity_type":   "Typedef",
				"entity_name":   "my_int",
				"relative_path": "src/types.h",
				"repo_id":       "repository:r_12345678",
				"language":      "c",
			},
		},
		{
			FactID:       "fact-3",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "content_entity",
			SourceRef: facts.Ref{
				SourceSystem: "git",
			},
			Payload: map[string]any{
				"entity_id":     "typealias-1",
				"entity_type":   "TypeAlias",
				"entity_name":   "UserID",
				"relative_path": "src/types.ts",
				"repo_id":       "repository:r_12345678",
				"language":      "typescript",
			},
		},
		{
			FactID:       "fact-4",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "content_entity",
			SourceRef: facts.Ref{
				SourceSystem: "git",
			},
			Payload: map[string]any{
				"entity_id":     "component-1",
				"entity_type":   "Component",
				"entity_name":   "Button",
				"relative_path": "src/Button.tsx",
				"repo_id":       "repository:r_12345678",
				"language":      "tsx",
			},
		},
		{
			FactID:       "fact-5",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "content_entity",
			SourceRef: facts.Ref{
				SourceSystem: "git",
			},
			Payload: map[string]any{
				"entity_id":     "function-1",
				"entity_type":   "Function",
				"entity_name":   "Helper",
				"relative_path": "src/helper.go",
				"repo_id":       "repository:r_12345678",
				"language":      "go",
			},
		},
		{
			FactID:       "fact-6",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "content_entity",
			SourceRef: facts.Ref{
				SourceSystem: "git",
			},
			Payload: map[string]any{
				"entity_id":     "js-function-1",
				"entity_type":   "Function",
				"entity_name":   "getTab",
				"relative_path": "src/app.js",
				"repo_id":       "repository:r_12345678",
				"language":      "javascript",
				"docstring":     "Returns the active tab.",
				"method_kind":   "getter",
			},
		},
	})
	if err != nil {
		t.Fatalf("Project() error = %v, want nil", err)
	}

	if got, want := result.Intents.Count, 5; got != want {
		t.Fatalf("result.Intents.Count = %d, want %d", got, want)
	}
	if got, want := result.Content.EntityCount, 2; got != want {
		t.Fatalf("result.Content.EntityCount = %d, want %d", got, want)
	}
	if got, want := len(intentWriter.calls), 1; got != want {
		t.Fatalf("intent writer call count = %d, want %d", got, want)
	}
	intents := intentWriter.calls[0]
	if got, want := len(intents), 5; got != want {
		t.Fatalf("len(intents) = %d, want %d", got, want)
	}
	for i, intent := range intents {
		if got, want := intent.Domain, reducer.DomainSemanticEntityMaterialization; got != want {
			t.Fatalf("intents[%d].Domain = %q, want %q", i, got, want)
		}
	}
	if got, want := intents[0].EntityKey, "annotation-1"; got != want {
		t.Fatalf("intents[0].EntityKey = %q, want %q", got, want)
	}
	if got, want := intents[1].EntityKey, "component-1"; got != want {
		t.Fatalf("intents[1].EntityKey = %q, want %q", got, want)
	}
	if got, want := intents[2].EntityKey, "js-function-1"; got != want {
		t.Fatalf("intents[2].EntityKey = %q, want %q", got, want)
	}
	if got, want := intents[3].EntityKey, "typealias-1"; got != want {
		t.Fatalf("intents[3].EntityKey = %q, want %q", got, want)
	}
	if got, want := intents[4].EntityKey, "typedef-1"; got != want {
		t.Fatalf("intents[4].EntityKey = %q, want %q", got, want)
	}
}

func TestBuildReducerIntentSkipsNonSemanticContentEntities(t *testing.T) {
	t.Parallel()

	_, ok := buildReducerIntent(facts.Envelope{
		FactID:       "fact-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		FactKind:     "content_entity",
		Payload: map[string]any{
			"entity_type": "Function",
			"entity_id":   "function-1",
		},
	})
	if ok {
		t.Fatal("buildReducerIntent() ok = true for Function, want false")
	}
}

func TestBuildReducerIntentQueuesJavaScriptCallableSemanticEntities(t *testing.T) {
	t.Parallel()

	intent, ok := buildSemanticEntityReducerIntent(facts.Envelope{
		FactID:       "fact-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		FactKind:     "content_entity",
		Payload: map[string]any{
			"entity_type":   "Function",
			"entity_id":     "js-function-1",
			"entity_name":   "getTab",
			"relative_path": "src/app.js",
			"repo_id":       "repo-1",
			"language":      "javascript",
			"docstring":     "Returns the active tab.",
			"method_kind":   "getter",
		},
	})
	if !ok {
		t.Fatal("buildSemanticEntityReducerIntent() ok = false for JavaScript Function, want true")
	}
	if got, want := intent.Domain, reducer.DomainSemanticEntityMaterialization; got != want {
		t.Fatalf("intent.Domain = %q, want %q", got, want)
	}
	if got, want := intent.EntityKey, "js-function-1"; got != want {
		t.Fatalf("intent.EntityKey = %q, want %q", got, want)
	}
}

type recordingCanonicalWriter struct {
	calls []CanonicalMaterialization
}

func (w *recordingCanonicalWriter) Write(_ context.Context, mat CanonicalMaterialization) error {
	w.calls = append(w.calls, mat)
	return nil
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

func TestRuntimeProjectWithTelemetry(t *testing.T) {
	t.Parallel()

	tracer := noop.NewTracerProvider().Tracer("test")
	meter := metricnoop.NewMeterProvider().Meter("test")
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		t.Fatalf("NewInstruments() error = %v, want nil", err)
	}

	canonicalWriter := &recordingCanonicalWriter{}
	contentWriter := &recordingContentWriter{result: content.Result{RecordCount: 1}}
	intentWriter := &recordingIntentWriter{result: IntentResult{Count: 1}}

	runtime := Runtime{
		CanonicalWriter: canonicalWriter,
		ContentWriter:   contentWriter,
		IntentWriter:    intentWriter,
		Tracer:          tracer,
		Instruments:     instruments,
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
			FactID:       "fact-0",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "repository",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
			Payload: map[string]any{
				"repo_id": "repo-123",
				"name":    "platform-context-graph",
				"path":    "org/platform-context-graph",
			},
		},
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
	if got, want := len(canonicalWriter.calls), 1; got < want {
		t.Fatalf("canonical writer call count = %d, want >= %d", got, want)
	}
	if got, want := len(contentWriter.calls), 1; got != want {
		t.Fatalf("content writer call count = %d, want %d", got, want)
	}
	if got, want := len(intentWriter.calls), 1; got != want {
		t.Fatalf("intent writer call count = %d, want %d", got, want)
	}
	if got, want := result.Content.RecordCount, 1; got != want {
		t.Fatalf("result.Content.RecordCount = %d, want %d", got, want)
	}
	if got, want := result.Intents.Count, 1; got != want {
		t.Fatalf("result.Intents.Count = %d, want %d", got, want)
	}
}
