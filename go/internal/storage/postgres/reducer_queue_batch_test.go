package postgres

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestClaimBatchValidationRejectsEmptyQueue(t *testing.T) {
	t.Parallel()

	q := ReducerQueue{}
	_, err := q.ClaimBatch(context.Background(), 5)
	if err == nil {
		t.Fatal("ClaimBatch() with zero-value queue should fail validation")
	}
}

func TestAckBatchValidationRejectsEmptyQueue(t *testing.T) {
	t.Parallel()

	q := ReducerQueue{}
	err := q.AckBatch(context.Background(), []reducer.Intent{{IntentID: "test"}}, nil)
	if err == nil {
		t.Fatal("AckBatch() with zero-value queue should fail validation")
	}
}

func TestAckBatchEmptyIsNoop(t *testing.T) {
	t.Parallel()

	q := ReducerQueue{
		db:            &fakeExecQueryer{},
		LeaseOwner:    "test",
		LeaseDuration: time.Minute,
	}

	err := q.AckBatch(context.Background(), nil, nil)
	if err != nil {
		t.Fatalf("AckBatch(nil) error = %v, want nil", err)
	}
}

func TestClaimBatchReturnsEmptyFromEmptyDB(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{rows: nil}, // empty result set
		},
	}
	q := ReducerQueue{
		db:            db,
		LeaseOwner:    "test",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC) },
	}

	intents, err := q.ClaimBatch(context.Background(), 5)
	if err != nil {
		t.Fatalf("ClaimBatch() error = %v", err)
	}
	if len(intents) != 0 {
		t.Fatalf("ClaimBatch() returned %d intents from empty db, want 0", len(intents))
	}
}

func TestClaimBatchReturnsClaimedIntents(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{rows: [][]any{
				{"item-1", "scope-1", "gen-1", "code_call_materialization", 1, now, now, []byte(`{"entity_key":"key-1","reason":"test","fact_id":"f1","source_system":"git"}`)},
				{"item-2", "scope-2", "gen-2", "code_call_materialization", 1, now, now, []byte(`{"entity_key":"key-2","reason":"test","fact_id":"f2","source_system":"git"}`)},
			}},
		},
	}
	q := ReducerQueue{
		db:            db,
		LeaseOwner:    "test",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return now },
	}

	intents, err := q.ClaimBatch(context.Background(), 5)
	if err != nil {
		t.Fatalf("ClaimBatch() error = %v", err)
	}
	if got, want := len(intents), 2; got != want {
		t.Fatalf("ClaimBatch() returned %d intents, want %d", got, want)
	}
	if intents[0].IntentID != "item-1" {
		t.Fatalf("intents[0].IntentID = %q, want %q", intents[0].IntentID, "item-1")
	}
	if intents[1].IntentID != "item-2" {
		t.Fatalf("intents[1].IntentID = %q, want %q", intents[1].IntentID, "item-2")
	}
}

func TestReducerQueueImplementsBatchInterfaces(t *testing.T) {
	t.Parallel()

	q := NewReducerQueue(&fakeExecQueryer{}, "test", time.Minute)

	// Compile-time check that ReducerQueue implements both batch interfaces.
	var _ reducer.BatchWorkSource = q
	var _ reducer.BatchWorkSink = q
}
