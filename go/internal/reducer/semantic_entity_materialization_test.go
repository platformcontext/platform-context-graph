package reducer

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractSemanticEntityRowsFiltersAnnotationAndTypedefFacts(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-1",
			},
		},
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/Logged.java",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "annotation-1",
				"relative_path": "src/Logged.java",
				"entity_type":   "Annotation",
				"entity_name":   "Logged",
				"language":      "java",
				"start_line":    12,
				"end_line":      12,
				"entity_metadata": map[string]any{
					"kind":        "applied",
					"target_kind": "method_declaration",
				},
			},
		},
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/types.h",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "typedef-1",
				"relative_path": "src/types.h",
				"entity_type":   "Typedef",
				"entity_name":   "my_int",
				"language":      "c",
				"start_line":    3,
				"end_line":      3,
				"entity_metadata": map[string]any{
					"type": "int",
				},
			},
		},
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/types.ts",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "alias-1",
				"relative_path": "src/types.ts",
				"entity_type":   "TypeAlias",
				"entity_name":   "UserID",
			},
		},
	}

	repoIDs, rows := ExtractSemanticEntityRows(envelopes)

	if got, want := repoIDs, []string{"repo-1"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("ExtractSemanticEntityRows() repoIDs = %v, want %v", got, want)
	}
	if got, want := len(rows), 2; got != want {
		t.Fatalf("ExtractSemanticEntityRows() rows = %d, want %d", got, want)
	}

	annotation := rows[0]
	if annotation.EntityType != "Annotation" {
		t.Fatalf("rows[0].EntityType = %q, want Annotation", annotation.EntityType)
	}
	if annotation.EntityID != "annotation-1" {
		t.Fatalf("rows[0].EntityID = %q, want annotation-1", annotation.EntityID)
	}
	if annotation.FilePath != "/repo/src/Logged.java" {
		t.Fatalf("rows[0].FilePath = %q, want /repo/src/Logged.java", annotation.FilePath)
	}
	if got, want := annotation.Metadata["kind"], "applied"; got != want {
		t.Fatalf("rows[0].Metadata[kind] = %v, want %v", got, want)
	}

	typedef := rows[1]
	if typedef.EntityType != "Typedef" {
		t.Fatalf("rows[1].EntityType = %q, want Typedef", typedef.EntityType)
	}
	if typedef.EntityID != "typedef-1" {
		t.Fatalf("rows[1].EntityID = %q, want typedef-1", typedef.EntityID)
	}
	if got, want := typedef.Metadata["type"], "int"; got != want {
		t.Fatalf("rows[1].Metadata[type] = %v, want %v", got, want)
	}
}

func TestSemanticEntityMaterializationHandlerWritesAndRetracts(t *testing.T) {
	t.Parallel()

	loader := &fakeSemanticEntityFactLoader{
		envelopes: []facts.Envelope{
			{
				FactKind: "repository",
				Payload: map[string]any{
					"repo_id": "repo-1",
				},
			},
			{
				FactKind: "content_entity",
				SourceRef: facts.Ref{
					SourceURI: "/repo/src/Logged.java",
				},
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "annotation-1",
					"relative_path": "src/Logged.java",
					"entity_type":   "Annotation",
					"entity_name":   "Logged",
					"language":      "java",
					"start_line":    12,
					"end_line":      12,
					"entity_metadata": map[string]any{
						"kind":        "applied",
						"target_kind": "method_declaration",
					},
				},
			},
			{
				FactKind: "content_entity",
				SourceRef: facts.Ref{
					SourceURI: "/repo/src/types.h",
				},
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "typedef-1",
					"relative_path": "src/types.h",
					"entity_type":   "Typedef",
					"entity_name":   "my_int",
					"language":      "c",
					"start_line":    3,
					"end_line":      3,
					"entity_metadata": map[string]any{
						"type": "int",
					},
				},
			},
		},
	}
	writer := &recordingSemanticEntityWriter{
		result: SemanticEntityWriteResult{
			CanonicalWrites: 2,
		},
	}

	handler := SemanticEntityMaterializationHandler{
		FactLoader: loader,
		Writer:     writer,
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-1",
		ScopeID:      "scope-1",
		GenerationID: "generation-1",
		SourceSystem: "git",
		Domain:       DomainSemanticEntityMaterialization,
		Cause:        "semantic entity follow-up",
		Status:       IntentStatusClaimed,
		EnqueuedAt:   time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC),
		AvailableAt:  time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if got, want := result.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("Handle().Status = %q, want %q", got, want)
	}
	if got, want := len(writer.writes), 1; got != want {
		t.Fatalf("writer writes = %d, want %d", got, want)
	}
	if got, want := len(writer.writes[0].RepoIDs), 1; got != want {
		t.Fatalf("writer RepoIDs = %v, want 1 repo", writer.writes[0].RepoIDs)
	}
	if got, want := len(writer.writes[0].Rows), 2; got != want {
		t.Fatalf("writer Rows = %d, want %d", got, want)
	}
}

func TestSemanticEntityMaterializationHandlerRetractsWhenNoTargetRowsRemain(t *testing.T) {
	t.Parallel()

	loader := &fakeSemanticEntityFactLoader{
		envelopes: []facts.Envelope{
			{
				FactKind: "repository",
				Payload: map[string]any{
					"repo_id": "repo-1",
				},
			},
			{
				FactKind: "content_entity",
				SourceRef: facts.Ref{
					SourceURI: "/repo/src/types.ts",
				},
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "alias-1",
					"relative_path": "src/types.ts",
					"entity_type":   "TypeAlias",
					"entity_name":   "UserID",
				},
			},
		},
	}
	writer := &recordingSemanticEntityWriter{
		result: SemanticEntityWriteResult{},
	}

	handler := SemanticEntityMaterializationHandler{
		FactLoader: loader,
		Writer:     writer,
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-2",
		ScopeID:      "scope-1",
		GenerationID: "generation-1",
		SourceSystem: "git",
		Domain:       DomainSemanticEntityMaterialization,
		Cause:        "semantic entity follow-up",
		Status:       IntentStatusClaimed,
		EnqueuedAt:   time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC),
		AvailableAt:  time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if got, want := result.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("Handle().Status = %q, want %q", got, want)
	}
	if got, want := len(writer.writes), 1; got != want {
		t.Fatalf("writer writes = %d, want %d", got, want)
	}
	if got, want := len(writer.writes[0].RepoIDs), 1; got != want {
		t.Fatalf("writer RepoIDs = %v, want 1 repo", writer.writes[0].RepoIDs)
	}
	if got, want := len(writer.writes[0].Rows), 0; got != want {
		t.Fatalf("writer Rows = %d, want %d", got, want)
	}
}

func TestNewDefaultRuntimeRegistersSemanticEntityMaterializationWhenWriterPresent(t *testing.T) {
	t.Parallel()

	runtime, err := NewDefaultRuntime(DefaultHandlers{
		WorkloadIdentityWriter: &recordingWorkloadIdentityWriter{
			result: WorkloadIdentityWriteResult{CanonicalWrites: 1},
		},
		CloudAssetResolutionWriter: &recordingCloudAssetResolutionWriter{
			result: CloudAssetResolutionWriteResult{CanonicalWrites: 1},
		},
		PlatformMaterializationWriter: &recordingPlatformMaterializationWriter{
			result: PlatformMaterializationWriteResult{CanonicalWrites: 1},
		},
		SemanticEntityWriter: &recordingSemanticEntityWriter{
			result: SemanticEntityWriteResult{CanonicalWrites: 1},
		},
		FactLoader: &fakeSemanticEntityFactLoader{
			envelopes: []facts.Envelope{
				{
					FactKind: "repository",
					Payload: map[string]any{
						"repo_id": "repo-1",
					},
				},
				{
					FactKind: "content_entity",
					SourceRef: facts.Ref{
						SourceURI:    "/repo/src/Logged.java",
						SourceSystem: "git",
					},
					Payload: map[string]any{
						"repo_id":       "repo-1",
						"entity_id":     "annotation-1",
						"relative_path": "src/Logged.java",
						"entity_type":   "Annotation",
						"entity_name":   "Logged",
						"language":      "java",
						"start_line":    12,
						"end_line":      12,
						"entity_metadata": map[string]any{
							"kind":        "applied",
							"target_kind": "method_declaration",
						},
					},
				},
			},
		},
		CodeCallEdgeWriter: &recordingCodeCallEdgeWriter{},
	})
	if err != nil {
		t.Fatalf("NewDefaultRuntime() error = %v, want nil", err)
	}

	_, err = runtime.Execute(context.Background(), Intent{
		IntentID:     "intent-semantic-1",
		ScopeID:      "scope-1",
		GenerationID: "generation-1",
		SourceSystem: "git",
		Domain:       DomainSemanticEntityMaterialization,
		Cause:        "semantic entity follow-up",
		Status:       IntentStatusClaimed,
		EnqueuedAt:   time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC),
		AvailableAt:  time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("runtime.Execute(semantic_entity_materialization) error = %v, want nil", err)
	}
}

type fakeSemanticEntityFactLoader struct {
	envelopes []facts.Envelope
}

func (f *fakeSemanticEntityFactLoader) ListFacts(context.Context, string, string) ([]facts.Envelope, error) {
	return append([]facts.Envelope(nil), f.envelopes...), nil
}

type recordingSemanticEntityWriter struct {
	writes []SemanticEntityWrite
	result SemanticEntityWriteResult
}

func (w *recordingSemanticEntityWriter) WriteSemanticEntities(
	_ context.Context,
	write SemanticEntityWrite,
) (SemanticEntityWriteResult, error) {
	w.writes = append(w.writes, write)
	return w.result, nil
}
