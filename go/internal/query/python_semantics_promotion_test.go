package query

import (
	"reflect"
	"testing"
)

func TestPythonSemanticProfileFromMetadata(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		entityType  string
		metadata    map[string]any
		wantSignals []PythonSemanticSignal
		wantKind    string
	}{
		{
			name:       "decorated async function with annotations",
			entityType: "Function",
			metadata: map[string]any{
				"decorators":       []any{"@route", "@cached"},
				"async":            true,
				"type_annotations": []any{map[string]any{"annotation_kind": "parameter"}},
			},
			wantSignals: []PythonSemanticSignal{
				PythonSemanticSignalDecorator,
				PythonSemanticSignalAsync,
				PythonSemanticSignalTypeAnnotation,
			},
			wantKind: "decorated_async_function",
		},
		{
			name:       "function with compact type annotation projection",
			entityType: "Function",
			metadata: map[string]any{
				"type_annotation_count": 2,
				"type_annotation_kinds": []any{"parameter", "return"},
			},
			wantSignals: []PythonSemanticSignal{
				PythonSemanticSignalTypeAnnotation,
			},
			wantKind: "type_annotation",
		},
		{
			name:       "type annotation entity",
			entityType: "TypeAnnotation",
			metadata: map[string]any{
				"type":            "str",
				"annotation_kind": "parameter",
				"context":         "greet",
			},
			wantSignals: []PythonSemanticSignal{
				PythonSemanticSignalTypeAnnotation,
			},
			wantKind: "parameter_type_annotation",
		},
		{
			name:       "return type annotation entity",
			entityType: "TypeAnnotation",
			metadata: map[string]any{
				"type":            "str",
				"annotation_kind": "return",
				"context":         "greet",
			},
			wantSignals: []PythonSemanticSignal{
				PythonSemanticSignalTypeAnnotation,
			},
			wantKind: "return_type_annotation",
		},
		{
			name:       "lambda function",
			entityType: "Function",
			metadata: map[string]any{
				"semantic_kind": "lambda",
			},
			wantSignals: []PythonSemanticSignal{
				PythonSemanticSignalLambda,
			},
			wantKind: "lambda_function",
		},
		{
			name:       "class with metaclass",
			entityType: "Class",
			metadata: map[string]any{
				"metaclass": "MetaLogger",
			},
			wantSignals: []PythonSemanticSignal{
				PythonSemanticSignalMetaclass,
			},
			wantKind: "metaclass_class",
		},
		{
			name:       "class with docstring only",
			entityType: "Class",
			metadata: map[string]any{
				"docstring": "Represents a configured logger.",
			},
			wantKind: "documented_class",
		},
		{
			name:       "function with docstring only",
			entityType: "Function",
			metadata: map[string]any{
				"docstring": "Handles incoming requests.",
			},
			wantKind: "documented_function",
		},
		{
			name:        "plain python function",
			entityType:  "Function",
			metadata:    map[string]any{},
			wantSignals: nil,
			wantKind:    "plain",
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			profile := PythonSemanticProfileFromMetadata(tt.entityType, tt.metadata)

			if got, want := profile.Signals(), tt.wantSignals; !reflect.DeepEqual(got, want) {
				t.Fatalf("Signals() = %#v, want %#v", got, want)
			}
			if got, want := profile.SurfaceKind(), tt.wantKind; got != want {
				t.Fatalf("SurfaceKind() = %q, want %q", got, want)
			}
		})
	}
}

func TestPythonSemanticProfilePriority(t *testing.T) {
	t.Parallel()

	profile := PythonSemanticProfileFromMetadata("Function", map[string]any{
		"decorators": []any{"@route"},
		"async":      true,
	})

	if !profile.HasSignals() {
		t.Fatal("HasSignals() = false, want true")
	}
	if got, want := profile.PrimarySignal(), PythonSemanticSignalDecorator; got != want {
		t.Fatalf("PrimarySignal() = %q, want %q", got, want)
	}
}
