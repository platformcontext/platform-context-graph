package neo4j

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
)

func TestBuildPlanMaterializesSourceLocalNodeUpsertsAndTombstoneDeletes(t *testing.T) {
	t.Parallel()

	materialization := graph.Materialization{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		SourceSystem: "git",
		Records: []graph.Record{
			{
				RecordID: "record-1",
				Kind:     "repository",
				Attributes: map[string]string{
					"name":     "platform-context-graph",
					"language": "go",
				},
			},
			{
				RecordID: "record-2",
				Deleted:  true,
			},
		},
	}

	plan, err := BuildPlan(materialization)
	if err != nil {
		t.Fatalf("BuildPlan() error = %v, want nil", err)
	}

	if got, want := plan.ScopeID, "scope-123"; got != want {
		t.Fatalf("plan.ScopeID = %q, want %q", got, want)
	}
	if got, want := plan.GenerationID, "generation-456"; got != want {
		t.Fatalf("plan.GenerationID = %q, want %q", got, want)
	}
	if got, want := len(plan.Statements), 2; got != want {
		t.Fatalf("len(plan.Statements) = %d, want %d", got, want)
	}

	upsert := plan.Statements[0]
	if got, want := upsert.Operation, OperationUpsertNode; got != want {
		t.Fatalf("upsert.Operation = %q, want %q", got, want)
	}
	if got, want := upsert.Cypher, upsertNodeCypher; got != want {
		t.Fatalf("upsert.Cypher = %q, want %q", got, want)
	}
	if got, want := upsert.Parameters["scope_id"], "scope-123"; got != want {
		t.Fatalf("upsert.Parameters[scope_id] = %v, want %q", got, want)
	}
	if got, want := upsert.Parameters["generation_id"], "generation-456"; got != want {
		t.Fatalf("upsert.Parameters[generation_id] = %v, want %q", got, want)
	}
	if got, want := upsert.Parameters["record_id"], "record-1"; got != want {
		t.Fatalf("upsert.Parameters[record_id] = %v, want %q", got, want)
	}
	if got, want := upsert.Parameters["source_system"], "git"; got != want {
		t.Fatalf("upsert.Parameters[source_system] = %v, want %q", got, want)
	}
	if got, want := upsert.Parameters["kind"], "repository"; got != want {
		t.Fatalf("upsert.Parameters[kind] = %v, want %q", got, want)
	}
	if _, ok := upsert.Parameters["attributes"]; ok {
		t.Fatal("upsert.Parameters[attributes] present, want serialized attributes_json only")
	}
	attributesJSON, ok := upsert.Parameters["attributes_json"].(string)
	if !ok {
		t.Fatalf("upsert.Parameters[attributes_json] type = %T, want string", upsert.Parameters["attributes_json"])
	}
	var attributes map[string]string
	if err := json.Unmarshal([]byte(attributesJSON), &attributes); err != nil {
		t.Fatalf("json.Unmarshal(attributes_json) error = %v, want nil", err)
	}
	if got, want := attributes["name"], "platform-context-graph"; got != want {
		t.Fatalf("upsert attributes[name] = %q, want %q", got, want)
	}
	if got, want := attributes["language"], "go"; got != want {
		t.Fatalf("upsert attributes[language] = %q, want %q", got, want)
	}

	deleteStmt := plan.Statements[1]
	if got, want := deleteStmt.Operation, OperationDeleteNode; got != want {
		t.Fatalf("deleteStmt.Operation = %q, want %q", got, want)
	}
	if got, want := deleteStmt.Cypher, deleteNodeCypher; got != want {
		t.Fatalf("deleteStmt.Cypher = %q, want %q", got, want)
	}
	if got, want := deleteStmt.Parameters["record_id"], "record-2"; got != want {
		t.Fatalf("deleteStmt.Parameters[record_id] = %v, want %q", got, want)
	}

	materialization.Records[0].Attributes["name"] = "mutated"
	if got, want := attributes["name"], "platform-context-graph"; got != want {
		t.Fatalf("plan attributes mutated with input = %q, want %q", got, want)
	}
}

func TestBuildPlanRejectsIncompleteSourceLocalInputs(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name            string
		materialization graph.Materialization
		wantErr         string
	}{
		{
			name: "missing scope",
			materialization: graph.Materialization{
				GenerationID: "generation-456",
				SourceSystem: "git",
				Records: []graph.Record{{
					RecordID: "record-1",
					Kind:     "repository",
				}},
			},
			wantErr: "scope_id must not be blank",
		},
		{
			name: "missing source system",
			materialization: graph.Materialization{
				ScopeID:      "scope-123",
				GenerationID: "generation-456",
				Records: []graph.Record{{
					RecordID: "record-1",
					Kind:     "repository",
				}},
			},
			wantErr: "source_system must not be blank",
		},
		{
			name: "missing record id",
			materialization: graph.Materialization{
				ScopeID:      "scope-123",
				GenerationID: "generation-456",
				SourceSystem: "git",
				Records: []graph.Record{{
					Kind: "repository",
				}},
			},
			wantErr: "record 0 record_id must not be blank",
		},
		{
			name: "missing kind on upsert",
			materialization: graph.Materialization{
				ScopeID:      "scope-123",
				GenerationID: "generation-456",
				SourceSystem: "git",
				Records: []graph.Record{{
					RecordID: "record-1",
				}},
			},
			wantErr: "record 0 kind must not be blank for source-local upsert",
		},
		{
			name: "tombstone delete without kind is allowed",
			materialization: graph.Materialization{
				ScopeID:      "scope-123",
				GenerationID: "generation-456",
				SourceSystem: "git",
				Records: []graph.Record{{
					RecordID: "record-1",
					Deleted:  true,
				}},
			},
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			plan, err := BuildPlan(tt.materialization)
			if tt.wantErr == "" {
				if err != nil {
					t.Fatalf("BuildPlan() error = %v, want nil", err)
				}
				if got, want := len(plan.Statements), 1; got != want {
					t.Fatalf("len(plan.Statements) = %d, want %d", got, want)
				}
				if got, want := plan.Statements[0].Operation, OperationDeleteNode; got != want {
					t.Fatalf("plan.Statements[0].Operation = %q, want %q", got, want)
				}
				return
			}

			if err == nil {
				t.Fatal("BuildPlan() error = nil, want non-nil")
			}
			if got := err.Error(); got != tt.wantErr {
				t.Fatalf("BuildPlan() error = %q, want %q", got, tt.wantErr)
			}
		})
	}
}

func TestAdapterWriteExecutesPlanInOrder(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	adapter := Adapter{Executor: executor}

	result, err := adapter.Write(context.Background(), graph.Materialization{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		SourceSystem: "git",
		Records: []graph.Record{
			{
				RecordID: "record-1",
				Kind:     "repository",
				Attributes: map[string]string{
					"name": "platform-context-graph",
				},
			},
			{
				RecordID: "record-2",
				Deleted:  true,
			},
		},
	})
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.RecordCount, 2; got != want {
		t.Fatalf("result.RecordCount = %d, want %d", got, want)
	}
	if got, want := result.DeletedCount, 1; got != want {
		t.Fatalf("result.DeletedCount = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("len(executor.calls) = %d, want %d", got, want)
	}
	if got, want := executor.calls[0].Operation, OperationUpsertNode; got != want {
		t.Fatalf("first operation = %q, want %q", got, want)
	}
	if got, want := executor.calls[1].Operation, OperationDeleteNode; got != want {
		t.Fatalf("second operation = %q, want %q", got, want)
	}
}

func TestAdapterWriteReturnsExecutorErrors(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{errAtCall: errors.New("boom")}
	adapter := Adapter{Executor: executor}

	_, err := adapter.Write(context.Background(), graph.Materialization{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		SourceSystem: "git",
		Records: []graph.Record{{
			RecordID: "record-1",
			Kind:     "repository",
		}},
	})
	if err == nil {
		t.Fatal("Write() error = nil, want non-nil")
	}
	if got, want := err.Error(), "execute source-local graph statement 0: boom"; got != want {
		t.Fatalf("Write() error = %q, want %q", got, want)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("len(executor.calls) = %d, want %d", got, want)
	}
}

type recordingExecutor struct {
	calls     []Statement
	errAtCall error
}

func (r *recordingExecutor) Execute(_ context.Context, statement Statement) error {
	r.calls = append(r.calls, statement)
	if r.errAtCall != nil {
		return r.errAtCall
	}

	return nil
}
