package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestSemanticEntityWriterWritesAnnotationTypedefTypeAliasComponentAndFunctionNodes(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewSemanticEntityWriter(executor, 0)

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows: []reducer.SemanticEntityRow{
			{
				RepoID:       "repo-1",
				EntityID:     "annotation-1",
				EntityType:   "Annotation",
				EntityName:   "Logged",
				FilePath:     "/repo/src/Logged.java",
				RelativePath: "src/Logged.java",
				Language:     "java",
				StartLine:    12,
				EndLine:      12,
				Metadata: map[string]any{
					"kind":        "applied",
					"target_kind": "method_declaration",
				},
			},
			{
				RepoID:       "repo-1",
				EntityID:     "typedef-1",
				EntityType:   "Typedef",
				EntityName:   "my_int",
				FilePath:     "/repo/src/types.h",
				RelativePath: "src/types.h",
				Language:     "c",
				StartLine:    3,
				EndLine:      3,
				Metadata: map[string]any{
					"type": "int",
				},
			},
			{
				RepoID:       "repo-1",
				EntityID:     "alias-1",
				EntityType:   "TypeAlias",
				EntityName:   "UserID",
				FilePath:     "/repo/src/types.ts",
				RelativePath: "src/types.ts",
				Language:     "typescript",
				StartLine:    8,
				EndLine:      8,
				Metadata: map[string]any{
					"type_alias_kind": "mapped_type",
					"type_parameters": []any{"T"},
				},
			},
			{
				RepoID:       "repo-1",
				EntityID:     "component-1",
				EntityType:   "Component",
				EntityName:   "Button",
				FilePath:     "/repo/src/Button.tsx",
				RelativePath: "src/Button.tsx",
				Language:     "tsx",
				StartLine:    4,
				EndLine:      4,
				Metadata: map[string]any{
					"framework":                "react",
					"jsx_fragment_shorthand":   true,
					"component_type_assertion": "ComponentType",
				},
			},
			{
				RepoID:       "repo-1",
				EntityID:     "function-1",
				EntityType:   "Function",
				EntityName:   "getTab",
				FilePath:     "/repo/src/app.js",
				RelativePath: "src/app.js",
				Language:     "javascript",
				StartLine:    10,
				EndLine:      24,
				Metadata: map[string]any{
					"docstring":   "Returns the active tab.",
					"method_kind": "getter",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 5; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 6; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if executor.calls[0].Operation != OperationCanonicalRetract {
		t.Fatalf("call[0].Operation = %q, want %q", executor.calls[0].Operation, OperationCanonicalRetract)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DETACH DELETE n") {
		t.Fatalf("call[0].Cypher missing DETACH DELETE: %s", executor.calls[0].Cypher)
	}

	annotationRows := executor.calls[1].Parameters["rows"].([]map[string]any)
	if got, want := len(annotationRows), 1; got != want {
		t.Fatalf("annotation row count = %d, want %d", got, want)
	}
	if got, want := annotationRows[0]["kind"], "applied"; got != want {
		t.Fatalf("annotation kind = %#v, want %#v", got, want)
	}
	if got, want := annotationRows[0]["target_kind"], "method_declaration"; got != want {
		t.Fatalf("annotation target_kind = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[1].Cypher, "MERGE (n:Annotation {uid: row.entity_id})") {
		t.Fatalf("annotation cypher missing Annotation merge: %s", executor.calls[1].Cypher)
	}

	typedefRows := executor.calls[2].Parameters["rows"].([]map[string]any)
	if got, want := len(typedefRows), 1; got != want {
		t.Fatalf("typedef row count = %d, want %d", got, want)
	}
	if got, want := typedefRows[0]["type"], "int"; got != want {
		t.Fatalf("typedef type = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[2].Cypher, "MERGE (n:Typedef {uid: row.entity_id})") {
		t.Fatalf("typedef cypher missing Typedef merge: %s", executor.calls[2].Cypher)
	}

	typeAliasRows := executor.calls[3].Parameters["rows"].([]map[string]any)
	if got, want := len(typeAliasRows), 1; got != want {
		t.Fatalf("type alias row count = %d, want %d", got, want)
	}
	if got, want := typeAliasRows[0]["type_alias_kind"], "mapped_type"; got != want {
		t.Fatalf("type alias kind = %#v, want %#v", got, want)
	}
	typeParameters, ok := typeAliasRows[0]["type_parameters"].([]string)
	if !ok {
		t.Fatalf("type alias type_parameters type = %T, want []string", typeAliasRows[0]["type_parameters"])
	}
	if got, want := len(typeParameters), 1; got != want || typeParameters[0] != "T" {
		t.Fatalf("type alias type_parameters = %#v, want [T]", typeParameters)
	}
	if !strings.Contains(executor.calls[3].Cypher, "MERGE (n:TypeAlias {uid: row.entity_id})") {
		t.Fatalf("type alias cypher missing TypeAlias merge: %s", executor.calls[3].Cypher)
	}

	componentRows := executor.calls[4].Parameters["rows"].([]map[string]any)
	if got, want := len(componentRows), 1; got != want {
		t.Fatalf("component row count = %d, want %d", got, want)
	}
	if got, want := componentRows[0]["framework"], "react"; got != want {
		t.Fatalf("component framework = %#v, want %#v", got, want)
	}
	if got, want := componentRows[0]["jsx_fragment_shorthand"], true; got != want {
		t.Fatalf("component jsx_fragment_shorthand = %#v, want %#v", got, want)
	}
	if got, want := componentRows[0]["component_type_assertion"], "ComponentType"; got != want {
		t.Fatalf("component component_type_assertion = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[4].Cypher, "MERGE (n:Component {uid: row.entity_id})") {
		t.Fatalf("component cypher missing Component merge: %s", executor.calls[4].Cypher)
	}

	functionRows := executor.calls[5].Parameters["rows"].([]map[string]any)
	if got, want := len(functionRows), 1; got != want {
		t.Fatalf("function row count = %d, want %d", got, want)
	}
	if got, want := functionRows[0]["docstring"], "Returns the active tab."; got != want {
		t.Fatalf("function docstring = %#v, want %#v", got, want)
	}
	if got, want := functionRows[0]["method_kind"], "getter"; got != want {
		t.Fatalf("function method_kind = %#v, want %#v", got, want)
	}
	if !strings.Contains(executor.calls[5].Cypher, "MERGE (n:Function {uid: row.entity_id})") {
		t.Fatalf("function cypher missing Function merge: %s", executor.calls[5].Cypher)
	}
}

func TestSemanticEntityWriterRetractsWithoutUpserts(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewSemanticEntityWriter(executor, 0)

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1", "repo-2"},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 0; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if executor.calls[0].Operation != OperationCanonicalRetract {
		t.Fatalf("call[0].Operation = %q, want %q", executor.calls[0].Operation, OperationCanonicalRetract)
	}
	repoIDs, ok := executor.calls[0].Parameters["repo_ids"].([]string)
	if !ok {
		t.Fatalf("repo_ids type = %T, want []string", executor.calls[0].Parameters["repo_ids"])
	}
	if got, want := len(repoIDs), 2; got != want {
		t.Fatalf("repo_ids length = %d, want %d", got, want)
	}
}
