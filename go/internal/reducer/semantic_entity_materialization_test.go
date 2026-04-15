package reducer

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractSemanticEntityRowsFiltersAnnotationTypedefTypeAliasComponentAndFunctionFacts(t *testing.T) {
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
				"language":      "typescript",
				"entity_metadata": map[string]any{
					"type_alias_kind": "mapped_type",
					"type_parameters": []any{"T"},
				},
			},
		},
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/Button.tsx",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "component-1",
				"relative_path": "src/Button.tsx",
				"entity_type":   "Component",
				"entity_name":   "Button",
				"language":      "tsx",
				"entity_metadata": map[string]any{
					"framework":                "react",
					"jsx_fragment_shorthand":   true,
					"component_type_assertion": "ComponentType",
				},
			},
		},
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/app.js",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "function-1",
				"relative_path": "src/app.js",
				"entity_type":   "Function",
				"entity_name":   "getTab",
				"language":      "javascript",
				"docstring":     "Returns the active tab.",
				"method_kind":   "getter",
			},
		},
	}

	repoIDs, rows := ExtractSemanticEntityRows(envelopes)

	if got, want := repoIDs, []string{"repo-1"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("ExtractSemanticEntityRows() repoIDs = %v, want %v", got, want)
	}
	if got, want := len(rows), 5; got != want {
		t.Fatalf("ExtractSemanticEntityRows() rows = %d, want %d", got, want)
	}

	rowsByType := make(map[string]SemanticEntityRow, len(rows))
	for _, row := range rows {
		rowsByType[row.EntityType] = row
	}

	annotation := rowsByType["Annotation"]
	if annotation.EntityType != "Annotation" {
		t.Fatalf("Annotation row missing")
	}
	if annotation.EntityID != "annotation-1" {
		t.Fatalf("Annotation.EntityID = %q, want annotation-1", annotation.EntityID)
	}
	if annotation.FilePath != "/repo/src/Logged.java" {
		t.Fatalf("Annotation.FilePath = %q, want /repo/src/Logged.java", annotation.FilePath)
	}
	if got, want := annotation.Metadata["kind"], "applied"; got != want {
		t.Fatalf("Annotation.Metadata[kind] = %v, want %v", got, want)
	}

	typedef := rowsByType["Typedef"]
	if typedef.EntityType != "Typedef" {
		t.Fatalf("Typedef row missing")
	}
	if typedef.EntityID != "typedef-1" {
		t.Fatalf("Typedef.EntityID = %q, want typedef-1", typedef.EntityID)
	}
	if got, want := typedef.Metadata["type"], "int"; got != want {
		t.Fatalf("Typedef.Metadata[type] = %v, want %v", got, want)
	}

	typeAlias := rowsByType["TypeAlias"]
	if typeAlias.EntityType != "TypeAlias" {
		t.Fatalf("TypeAlias row missing")
	}
	if got, want := typeAlias.Metadata["type_alias_kind"], "mapped_type"; got != want {
		t.Fatalf("TypeAlias.Metadata[type_alias_kind] = %v, want %v", got, want)
	}
	typeParameters, ok := typeAlias.Metadata["type_parameters"].([]any)
	if !ok {
		t.Fatalf("TypeAlias.Metadata[type_parameters] type = %T, want []any", typeAlias.Metadata["type_parameters"])
	}
	if got, want := len(typeParameters), 1; got != want || typeParameters[0] != "T" {
		t.Fatalf("TypeAlias.Metadata[type_parameters] = %#v, want [T]", typeParameters)
	}

	component := rowsByType["Component"]
	if component.EntityType != "Component" {
		t.Fatalf("Component row missing")
	}
	if got, want := component.Metadata["framework"], "react"; got != want {
		t.Fatalf("Component.Metadata[framework] = %v, want %v", got, want)
	}
	if got, want := component.Metadata["jsx_fragment_shorthand"], true; got != want {
		t.Fatalf("Component.Metadata[jsx_fragment_shorthand] = %v, want %v", got, want)
	}
	if got, want := component.Metadata["component_type_assertion"], "ComponentType"; got != want {
		t.Fatalf("Component.Metadata[component_type_assertion] = %v, want %v", got, want)
	}

	jsFunction := rowsByType["Function"]
	if jsFunction.EntityType != "Function" {
		t.Fatalf("Function row missing")
	}
	if got, want := jsFunction.Metadata["docstring"], "Returns the active tab."; got != want {
		t.Fatalf("Function.Metadata[docstring] = %v, want %v", got, want)
	}
	if got, want := jsFunction.Metadata["method_kind"], "getter"; got != want {
		t.Fatalf("Function.Metadata[method_kind] = %v, want %v", got, want)
	}
}

func TestExtractSemanticEntityRowsIncludesPythonDecoratedAsyncFunctionFacts(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/app.py",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "function-1",
				"relative_path": "src/app.py",
				"entity_type":   "Function",
				"entity_name":   "handler",
				"language":      "python",
				"decorators":    []any{"@route", "@cached"},
				"async":         true,
			},
		},
	}

	repoIDs, rows := ExtractSemanticEntityRows(envelopes)
	if got, want := repoIDs, []string{"repo-1"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("ExtractSemanticEntityRows() repoIDs = %v, want %v", got, want)
	}
	if got, want := len(rows), 1; got != want {
		t.Fatalf("ExtractSemanticEntityRows() rows = %d, want %d", got, want)
	}

	row := rows[0]
	if got, want := row.EntityType, "Function"; got != want {
		t.Fatalf("row.EntityType = %q, want %q", got, want)
	}
	if got, want := row.Metadata["async"], true; got != want {
		t.Fatalf("row.Metadata[async] = %#v, want %#v", got, want)
	}
	decorators, ok := row.Metadata["decorators"].([]string)
	if !ok {
		t.Fatalf("row.Metadata[decorators] type = %T, want []string", row.Metadata["decorators"])
	}
	if got, want := len(decorators), 2; got != want || decorators[0] != "@route" || decorators[1] != "@cached" {
		t.Fatalf("row.Metadata[decorators] = %#v, want [@route @cached]", decorators)
	}
}

func TestExtractSemanticEntityRowsIncludesElixirGuardFacts(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/lib/demo/macros.ex",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"entity_id":     "function-guard-1",
				"relative_path": "lib/demo/macros.ex",
				"entity_type":   "Function",
				"entity_name":   "is_even",
				"language":      "elixir",
				"start_line":    10,
				"end_line":      10,
				"semantic_kind": "guard",
			},
		},
	}

	repoIDs, rows := ExtractSemanticEntityRows(envelopes)
	if got, want := repoIDs, []string{"repo-1"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("ExtractSemanticEntityRows() repoIDs = %v, want %v", got, want)
	}
	if got, want := len(rows), 1; got != want {
		t.Fatalf("ExtractSemanticEntityRows() rows = %d, want %d", got, want)
	}

	row := rows[0]
	if got, want := row.EntityType, "Function"; got != want {
		t.Fatalf("row.EntityType = %q, want %q", got, want)
	}
	if got, want := row.Metadata["semantic_kind"], "guard"; got != want {
		t.Fatalf("row.Metadata[semantic_kind] = %#v, want %#v", got, want)
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
					"language":      "typescript",
					"entity_metadata": map[string]any{
						"type_alias_kind": "mapped_type",
						"type_parameters": []any{"T"},
					},
				},
			},
			{
				FactKind: "content_entity",
				SourceRef: facts.Ref{
					SourceURI: "/repo/src/Button.tsx",
				},
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "component-1",
					"relative_path": "src/Button.tsx",
					"entity_type":   "Component",
					"entity_name":   "Button",
					"language":      "tsx",
					"entity_metadata": map[string]any{
						"framework":                "react",
						"jsx_fragment_shorthand":   true,
						"component_type_assertion": "ComponentType",
					},
				},
			},
			{
				FactKind: "content_entity",
				SourceRef: facts.Ref{
					SourceURI: "/repo/src/app.js",
				},
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "function-1",
					"relative_path": "src/app.js",
					"entity_type":   "Function",
					"entity_name":   "getTab",
					"language":      "javascript",
					"docstring":     "Returns the active tab.",
					"method_kind":   "getter",
				},
			},
		},
	}
	writer := &recordingSemanticEntityWriter{
		result: SemanticEntityWriteResult{
			CanonicalWrites: 5,
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
	if got, want := len(writer.writes[0].Rows), 5; got != want {
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
					SourceURI: "/repo/src/helper.go",
				},
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "function-1",
					"relative_path": "src/helper.go",
					"entity_type":   "Function",
					"entity_name":   "Helper",
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
