package postgres

import (
	"context"
	"database/sql"
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
