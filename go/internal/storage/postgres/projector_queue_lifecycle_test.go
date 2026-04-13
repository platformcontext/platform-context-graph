package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

func TestProjectorQueueAckPromotesGenerationAndSupersedesPriorActive(t *testing.T) {
	t.Parallel()

	db := &recordingExecQueryer{}
	queue := NewProjectorQueue(db, "projector-1", 30*time.Second)
	queue.Now = func() time.Time {
		return time.Date(2026, time.April, 12, 14, 30, 0, 0, time.UTC)
	}

	work := projector.ScopeGenerationWork{
		Scope: scope.IngestionScope{ScopeID: "scope-123"},
		Generation: scope.ScopeGeneration{
			GenerationID: "generation-456",
		},
	}

	if err := queue.Ack(context.Background(), work, projector.Result{}); err != nil {
		t.Fatalf("Ack() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE scope_generations",
		"WHEN status = 'active' THEN 'superseded'",
		"WHEN generation_id = $3 THEN 'active'",
		"UPDATE ingestion_scopes",
		"active_generation_id = $3",
		"UPDATE fact_work_items",
		"status = 'succeeded'",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("Ack() query missing %q:\n%s", want, query)
		}
	}
}

func TestProjectorQueueFailMarksGenerationFailedWithoutClearingOtherActiveGeneration(t *testing.T) {
	t.Parallel()

	db := &recordingExecQueryer{}
	queue := NewProjectorQueue(db, "projector-1", 30*time.Second)
	queue.Now = func() time.Time {
		return time.Date(2026, time.April, 12, 14, 30, 0, 0, time.UTC)
	}

	work := projector.ScopeGenerationWork{
		Scope: scope.IngestionScope{ScopeID: "scope-123"},
		Generation: scope.ScopeGeneration{
			GenerationID: "generation-456",
		},
	}

	if err := queue.Fail(context.Background(), work, errProjectionFailed); err != nil {
		t.Fatalf("Fail() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE scope_generations",
		"status = 'failed'",
		"UPDATE ingestion_scopes",
		"active_generation_id = CASE",
		"UPDATE fact_work_items",
		"status = 'failed'",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("Fail() query missing %q:\n%s", want, query)
		}
	}
}

func TestProjectorQueueFailRetriesRetryableErrorWithinAttemptBudget(t *testing.T) {
	t.Parallel()

	db := &recordingExecQueryer{}
	queue := NewProjectorQueue(db, "projector-1", 30*time.Second)
	queue.RetryDelay = 2 * time.Minute
	queue.MaxAttempts = 3
	queue.Now = func() time.Time {
		return time.Date(2026, time.April, 12, 14, 30, 0, 0, time.UTC)
	}

	work := projector.ScopeGenerationWork{
		Scope: scope.IngestionScope{ScopeID: "scope-123"},
		Generation: scope.ScopeGeneration{
			GenerationID: "generation-456",
		},
		AttemptCount: 1,
	}

	if err := queue.Fail(context.Background(), work, &retryableTestError{message: "transient projector failure"}); err != nil {
		t.Fatalf("Fail() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE fact_work_items",
		"status = 'retrying'",
		"next_attempt_at = $5",
		"visible_at = $5",
		"failure_class = $2",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("Fail() retry query missing %q:\n%s", want, query)
		}
	}

	if got, want := db.execs[0].args[1], "projection_retryable"; got != want {
		t.Fatalf("failure class = %v, want %v", got, want)
	}
	if got, want := db.execs[0].args[4], queue.Now().Add(queue.RetryDelay); got != want {
		t.Fatalf("next attempt = %v, want %v", got, want)
	}
}

func TestProjectorQueueFailMarksRetryableErrorTerminalWhenAttemptBudgetExhausted(t *testing.T) {
	t.Parallel()

	db := &recordingExecQueryer{}
	queue := NewProjectorQueue(db, "projector-1", 30*time.Second)
	queue.MaxAttempts = 2
	queue.Now = func() time.Time {
		return time.Date(2026, time.April, 12, 14, 30, 0, 0, time.UTC)
	}

	work := projector.ScopeGenerationWork{
		Scope: scope.IngestionScope{ScopeID: "scope-123"},
		Generation: scope.ScopeGeneration{
			GenerationID: "generation-456",
		},
		AttemptCount: 2,
	}

	if err := queue.Fail(context.Background(), work, &retryableTestError{message: "still broken"}); err != nil {
		t.Fatalf("Fail() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE scope_generations",
		"status = 'failed'",
		"UPDATE fact_work_items",
		"status = 'failed'",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("Fail() terminal query missing %q:\n%s", want, query)
		}
	}
}

var errProjectionFailed = &testError{message: "projection failed"}

type testError struct {
	message string
}

func (e *testError) Error() string {
	return e.message
}

type retryableTestError struct {
	message string
}

func (e *retryableTestError) Error() string {
	return e.message
}

func (e *retryableTestError) Retryable() bool {
	return true
}

type recordingExecQueryer struct {
	execs []recordedExecCall
}

type recordedExecCall struct {
	query string
	args  []any
}

func (r *recordingExecQueryer) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	r.execs = append(r.execs, recordedExecCall{
		query: query,
		args:  append([]any(nil), args...),
	})
	return proofResult{}, nil
}

func (r *recordingExecQueryer) QueryContext(context.Context, string, ...any) (Rows, error) {
	return nil, nil
}
