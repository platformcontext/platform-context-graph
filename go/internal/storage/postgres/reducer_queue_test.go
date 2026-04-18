package postgres

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestReducerWorkItemIDDeterministic(t *testing.T) {
	t.Parallel()
	intent := projector.ReducerIntent{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		Domain:       "workload_identity",
		EntityKey:    "entity-1",
	}
	id1 := reducerWorkItemID(intent)
	id2 := reducerWorkItemID(intent)
	if id1 != id2 {
		t.Fatalf("expected deterministic ID, got %q and %q", id1, id2)
	}
	if !strings.HasPrefix(id1, "reducer_") {
		t.Fatalf("expected prefix 'reducer_', got %q", id1)
	}
}

func TestReducerWorkItemIDSanitizesSpecialChars(t *testing.T) {
	t.Parallel()
	intent := projector.ReducerIntent{
		ScopeID:      "org/repo",
		GenerationID: "gen:1",
		Domain:       "workload_identity",
		EntityKey:    "entity/key:value",
	}
	id := reducerWorkItemID(intent)
	if strings.Contains(id, "/") || strings.Contains(id, ":") {
		t.Fatalf("ID contains unsanitized chars: %q", id)
	}
}

func TestReducerQueueBatchEnqueue(t *testing.T) {
	t.Parallel()

	recorder := &reducerRecordingDB{}
	queue := NewReducerQueue(recorder, "test-owner", 30*time.Second)

	// Create 1200 intents to test batching (should use 3 batches: 500 + 500 + 200)
	intents := make([]projector.ReducerIntent, 1200)
	for i := 0; i < 1200; i++ {
		intents[i] = projector.ReducerIntent{
			ScopeID:      "scope-1",
			GenerationID: "gen-1",
			Domain:       reducer.DomainWorkloadIdentity,
			EntityKey:    "entity-" + string(rune('a'+i%26)),
			Reason:       "test-reason",
			FactID:       "fact-" + string(rune('a'+i%26)),
			SourceSystem: "test-system",
		}
	}

	ctx := context.Background()
	result, err := queue.Enqueue(ctx, intents)
	if err != nil {
		t.Fatalf("Enqueue failed: %v", err)
	}

	if result.Count != 1200 {
		t.Errorf("expected count 1200, got %d", result.Count)
	}

	// Should have called ExecContext 3 times (3 batches: 500 + 500 + 200)
	if recorder.execCount != 3 {
		t.Errorf("expected 3 ExecContext calls for 1200 intents, got %d", recorder.execCount)
	}

	// Verify the queries contain multi-row VALUE clauses (presence of multiple value tuples)
	for i, call := range recorder.execs {
		if !strings.Contains(call.query, "INSERT INTO fact_work_items") {
			t.Errorf("exec[%d] missing INSERT INTO fact_work_items", i)
		}
		if !strings.Contains(call.query, "VALUES") {
			t.Errorf("exec[%d] missing VALUES clause", i)
		}
		// Check that it's a batch by looking for multiple value tuples
		valueCount := strings.Count(call.query, "($")
		expectedSize := reducerEnqueueBatchSize
		if i == 2 {
			expectedSize = 200 // last batch
		}
		if valueCount != expectedSize {
			t.Errorf("exec[%d] has %d value tuples, expected %d", i, valueCount, expectedSize)
		}
	}
}

func TestReducerQueueReopenSucceededResetsSucceededWorkItemToPending(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 18, 12, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{
		execResults: []sql.Result{rowsAffectedResult{rowsAffected: 1}},
	}
	queue := ReducerQueue{
		db:  db,
		Now: func() time.Time { return now },
	}

	reopened, err := queue.ReopenSucceeded(context.Background(), "reducer_scope-1_gen-1_deployment_mapping_repo_1")
	if err != nil {
		t.Fatalf("ReopenSucceeded() error = %v, want nil", err)
	}
	if !reopened {
		t.Fatal("ReopenSucceeded() reopened = false, want true")
	}
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE fact_work_items",
		"status = 'pending'",
		"attempt_count = 0",
		"stage = 'reducer'",
		"status = 'succeeded'",
		"next_attempt_at = NULL",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("reopen query missing %q:\n%s", want, query)
		}
	}
	if got, want := db.execs[0].args[0], now; got != want {
		t.Fatalf("updated_at arg = %v, want %v", got, want)
	}
	if got, want := db.execs[0].args[1], "reducer_scope-1_gen-1_deployment_mapping_repo_1"; got != want {
		t.Fatalf("work item arg = %v, want %v", got, want)
	}
}

func TestReducerQueueReopenSucceededReturnsFalseWhenNoRowMatches(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{
		execResults: []sql.Result{rowsAffectedResult{}},
	}
	queue := ReducerQueue{db: db}

	reopened, err := queue.ReopenSucceeded(context.Background(), "missing-work-item")
	if err != nil {
		t.Fatalf("ReopenSucceeded() error = %v, want nil", err)
	}
	if reopened {
		t.Fatal("ReopenSucceeded() reopened = true, want false")
	}
}

func TestReducerQueueReopenSucceededWrapsExecError(t *testing.T) {
	t.Parallel()

	queue := ReducerQueue{
		db: &fakeExecQueryer{
			execErrors: []error{errors.New("boom")},
		},
	}

	_, err := queue.ReopenSucceeded(context.Background(), "work-item")
	if err == nil {
		t.Fatal("ReopenSucceeded() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "reopen succeeded reducer work") {
		t.Fatalf("ReopenSucceeded() error = %v, want wrapped reopen context", err)
	}
}

func TestReducerQueueCountInFlightByDomainReturnsCount(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{rows: [][]any{{3}}},
		},
	}
	queue := ReducerQueue{db: db}

	count, err := queue.CountInFlightByDomain(
		context.Background(),
		reducer.DomainDeploymentMapping,
	)
	if err != nil {
		t.Fatalf("CountInFlightByDomain() error = %v, want nil", err)
	}
	if got, want := count, 3; got != want {
		t.Fatalf("CountInFlightByDomain() = %d, want %d", got, want)
	}
	if got, want := len(db.queries), 1; got != want {
		t.Fatalf("query count = %d, want %d", got, want)
	}
	if !strings.Contains(db.queries[0].query, "status NOT IN ('succeeded', 'dead_letter')") {
		t.Fatalf("count query = %q, want terminal-status filter", db.queries[0].query)
	}
	if got, want := db.queries[0].args[0], string(reducer.DomainDeploymentMapping); got != want {
		t.Fatalf("domain arg = %v, want %v", got, want)
	}
}

func TestReducerQueueCountInFlightByDomainRejectsUnknownDomain(t *testing.T) {
	t.Parallel()

	queue := ReducerQueue{db: &fakeExecQueryer{}}

	_, err := queue.CountInFlightByDomain(context.Background(), reducer.Domain("not-real"))
	if err == nil {
		t.Fatal("CountInFlightByDomain() error = nil, want non-nil")
	}
}

// reducerRecordingDB records ExecContext calls for verification.
type reducerRecordingDB struct {
	execCount int
	execs     []reducerRecordedExec
}

type reducerRecordedExec struct {
	query string
	args  []any
}

func (r *reducerRecordingDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	r.execCount++
	r.execs = append(r.execs, reducerRecordedExec{
		query: query,
		args:  append([]any(nil), args...),
	})
	return reducerProofResult{}, nil
}

func (r *reducerRecordingDB) QueryContext(context.Context, string, ...any) (Rows, error) {
	return nil, nil
}

// reducerProofResult is a minimal sql.Result implementation for testing.
type reducerProofResult struct{}

func (reducerProofResult) LastInsertId() (int64, error) { return 0, nil }
func (reducerProofResult) RowsAffected() (int64, error) { return 1, nil }

type rowsAffectedResult struct {
	rowsAffected int64
}

func (r rowsAffectedResult) LastInsertId() (int64, error) { return 0, nil }
func (r rowsAffectedResult) RowsAffected() (int64, error) { return r.rowsAffected, nil }
