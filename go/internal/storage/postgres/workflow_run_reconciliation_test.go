package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/workflow"
)

func TestWorkflowControlStoreReconcileWorkflowRunsUpdatesRunAndCompleteness(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 20, 21, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{
				rows: [][]any{{
					"run-1",
					string(workflow.TriggerKindBootstrap),
					string(workflow.RunStatusReducerConverging),
					"[]",
					sql.NullString{},
					now.Add(-time.Minute),
					now.Add(-time.Minute),
					sql.NullTime{},
				}},
			},
			{
				rows: [][]any{{
					string(scope.CollectorGit),
					1,
					0,
					0,
					1,
					0,
				}},
			},
			{
				rows: [][]any{
					{string(scope.CollectorGit), "canonical_nodes_committed", 1},
					{string(scope.CollectorGit), "semantic_nodes_committed", 1},
				},
			},
		},
	}
	store := NewWorkflowControlStore(db)

	reconciled, err := store.ReconcileWorkflowRuns(context.Background(), now)
	if err != nil {
		t.Fatalf("ReconcileWorkflowRuns() error = %v, want nil", err)
	}
	if got, want := reconciled, 1; got != want {
		t.Fatalf("reconciled = %d, want %d", got, want)
	}
	if got, want := len(db.execs), 3; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if !strings.Contains(db.execs[0].query, "UPDATE workflow_runs") {
		t.Fatalf("first exec missing workflow_runs update: %s", db.execs[0].query)
	}
	if !strings.Contains(db.execs[1].query, "INSERT INTO workflow_run_completeness") {
		t.Fatalf("second exec missing workflow_run_completeness upsert: %s", db.execs[1].query)
	}
}

func TestWorkflowControlStoreReconcileWorkflowRunsReturnsZeroWhenNoRunsNeedWork(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{{rows: nil}},
	}
	store := NewWorkflowControlStore(db)

	reconciled, err := store.ReconcileWorkflowRuns(context.Background(), time.Date(2026, time.April, 20, 21, 5, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("ReconcileWorkflowRuns() error = %v, want nil", err)
	}
	if got, want := reconciled, 0; got != want {
		t.Fatalf("reconciled = %d, want %d", got, want)
	}
}
