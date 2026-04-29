package neo4j

import (
	"context"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestEdgeWriterCodeCallUsesExactLabelsWhenReducerProvidesEntityTypes(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":            "repo-a",
				"caller_entity_id":   "entity:function:caller",
				"callee_entity_id":   "entity:class:callee",
				"caller_entity_type": "Function",
				"callee_entity_type": "Class",
			},
		},
	}

	if err := writer.WriteEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/code-calls"); err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	cypher := executor.calls[0].Cypher
	if !strings.Contains(cypher, "MATCH (source:Function {uid: row.caller_entity_id})") {
		t.Fatalf("cypher missing exact Function source anchor: %s", cypher)
	}
	if !strings.Contains(cypher, "MATCH (target:Class {uid: row.callee_entity_id})") {
		t.Fatalf("cypher missing exact Class target anchor: %s", cypher)
	}
	if strings.Contains(cypher, "Function|Class|File") {
		t.Fatalf("cypher used broad code-entity label fallback: %s", cypher)
	}
	if strings.Contains(cypher, "coalesce(") {
		t.Fatalf("cypher used coalesce on known code-call fields: %s", cypher)
	}
}

func TestEdgeWriterCodeCallFallsBackForUnknownEntityTypes(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":          "repo-a",
				"caller_entity_id": "entity:function:caller",
				"callee_entity_id": "entity:function:callee",
			},
		},
	}

	if err := writer.WriteEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/code-calls"); err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "Function|Class|File") {
		t.Fatalf("fallback cypher missing broad code-entity labels: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterMetaclassUsesExactLabelsWhenReducerProvidesEntityTypes(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":            "repo-a",
				"source_entity_id":   "entity:class:source",
				"target_entity_id":   "entity:class:target",
				"source_entity_type": "Class",
				"target_entity_type": "Class",
				"relationship_type":  "USES_METACLASS",
			},
		},
	}

	if err := writer.WriteEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/python-metaclass"); err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	cypher := executor.calls[0].Cypher
	if !strings.Contains(cypher, "MATCH (source:Class {uid: row.source_entity_id})") {
		t.Fatalf("cypher missing exact Class source anchor: %s", cypher)
	}
	if !strings.Contains(cypher, "MATCH (target:Class {uid: row.target_entity_id})") {
		t.Fatalf("cypher missing exact Class target anchor: %s", cypher)
	}
	if strings.Contains(cypher, "Function|Class|File") {
		t.Fatalf("cypher used broad code-entity label fallback: %s", cypher)
	}
}
