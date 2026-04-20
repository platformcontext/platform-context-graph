package neo4j

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"
)

type failingExecutor struct {
	calls   atomic.Int32
	failFor int    // fail this many times then succeed
	errMsg  string // error message to return
}

func (f *failingExecutor) Execute(_ context.Context, _ Statement) error {
	n := int(f.calls.Add(1))
	if n <= f.failFor {
		return errors.New(f.errMsg)
	}
	return nil
}

// groupCapableExecutor implements both Executor and GroupExecutor for testing.
type groupCapableExecutor struct {
	executeCalls      atomic.Int32
	executeGroupCalls atomic.Int32
	groupStmts        []Statement
	groupErr          error
}

func (g *groupCapableExecutor) Execute(_ context.Context, _ Statement) error {
	g.executeCalls.Add(1)
	return nil
}

func (g *groupCapableExecutor) ExecuteGroup(_ context.Context, stmts []Statement) error {
	g.executeGroupCalls.Add(1)
	g.groupStmts = stmts
	return g.groupErr
}

func TestRetryingExecutorRetriesOnDeadlock(t *testing.T) {
	t.Parallel()

	inner := &failingExecutor{
		failFor: 2,
		errMsg:  "Neo4jError: Neo.TransientError.Transaction.DeadlockDetected (deadlock cycle)",
	}

	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 3,
		BaseDelay:  1 * time.Millisecond,
	}

	err := r.Execute(context.Background(), Statement{Operation: OperationCanonicalUpsert})
	if err != nil {
		t.Fatalf("expected success after retries, got: %v", err)
	}
	if got := int(inner.calls.Load()); got != 3 {
		t.Errorf("calls = %d, want 3 (2 failures + 1 success)", got)
	}
}

func TestRetryingExecutorDoesNotRetryPermanentErrors(t *testing.T) {
	t.Parallel()

	inner := &failingExecutor{
		failFor: 10,
		errMsg:  "Neo4jError: Neo.ClientError.Schema.ConstraintValidationFailed",
	}

	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 3,
		BaseDelay:  1 * time.Millisecond,
	}

	err := r.Execute(context.Background(), Statement{Operation: OperationCanonicalUpsert})
	if err == nil {
		t.Fatal("expected error for permanent failure")
	}
	if got := int(inner.calls.Load()); got != 1 {
		t.Errorf("calls = %d, want 1 (no retry for permanent error)", got)
	}
}

func TestRetryingExecutorExhaustsRetries(t *testing.T) {
	t.Parallel()

	inner := &failingExecutor{
		failFor: 10,
		errMsg:  "Neo4jError: Neo.TransientError.Transaction.DeadlockDetected",
	}

	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 2,
		BaseDelay:  1 * time.Millisecond,
	}

	err := r.Execute(context.Background(), Statement{Operation: OperationCanonicalUpsert})
	if err == nil {
		t.Fatal("expected error after exhausting retries")
	}
	// 1 initial + 2 retries = 3 calls
	if got := int(inner.calls.Load()); got != 3 {
		t.Errorf("calls = %d, want 3 (initial + 2 retries)", got)
	}
}

func TestRetryingExecutorPassesThroughOnSuccess(t *testing.T) {
	t.Parallel()

	inner := &failingExecutor{failFor: 0} // never fails

	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 3,
		BaseDelay:  1 * time.Millisecond,
	}

	err := r.Execute(context.Background(), Statement{Operation: OperationCanonicalUpsert})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := int(inner.calls.Load()); got != 1 {
		t.Errorf("calls = %d, want 1", got)
	}
}

func TestRetryingExecutorRespectsContextCancellation(t *testing.T) {
	t.Parallel()

	inner := &failingExecutor{
		failFor: 10,
		errMsg:  "Neo4jError: Neo.TransientError.Transaction.DeadlockDetected",
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 5,
		BaseDelay:  1 * time.Millisecond,
	}

	err := r.Execute(ctx, Statement{Operation: OperationCanonicalUpsert})
	if err == nil {
		t.Fatal("expected error on cancelled context")
	}
}

func TestRetryingExecutorForwardsExecuteGroup(t *testing.T) {
	t.Parallel()

	inner := &groupCapableExecutor{}
	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 3,
		BaseDelay:  1 * time.Millisecond,
	}

	stmts := []Statement{
		{Operation: OperationCanonicalRetract, Cypher: "MATCH (d) DETACH DELETE d"},
		{Operation: OperationCanonicalUpsert, Cypher: "MERGE (f:File {path: $path})"},
	}

	err := r.ExecuteGroup(context.Background(), stmts)
	if err != nil {
		t.Fatalf("ExecuteGroup() error = %v", err)
	}

	if got := int(inner.executeGroupCalls.Load()); got != 1 {
		t.Errorf("executeGroupCalls = %d, want 1", got)
	}
	if got := int(inner.executeCalls.Load()); got != 0 {
		t.Errorf("executeCalls = %d, want 0 (should not fall back to Execute)", got)
	}
	if len(inner.groupStmts) != 2 {
		t.Errorf("forwarded stmts = %d, want 2", len(inner.groupStmts))
	}
}

func TestRetryingExecutorExecuteGroupErrorsWithoutGroupExecutor(t *testing.T) {
	t.Parallel()

	inner := &failingExecutor{failFor: 0} // only implements Executor, not GroupExecutor
	r := &RetryingExecutor{
		Inner:      inner,
		MaxRetries: 3,
		BaseDelay:  1 * time.Millisecond,
	}

	err := r.ExecuteGroup(context.Background(), []Statement{{Cypher: "test"}})
	if err == nil {
		t.Fatal("expected error when Inner does not implement GroupExecutor")
	}
}

func TestIsTransientNeo4jError(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		err      error
		expected bool
	}{
		{"nil", nil, false},
		{"deadlock", errors.New("Neo.TransientError.Transaction.DeadlockDetected"), true},
		{"transient generic", errors.New("something TransientError something"), true},
		{"lock client", errors.New("LockClient timeout"), true},
		{"constraint violation", errors.New("Neo.ClientError.Schema.ConstraintValidationFailed"), false},
		{"generic error", errors.New("connection refused"), false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := isTransientNeo4jError(tt.err)
			if got != tt.expected {
				t.Errorf("isTransientNeo4jError(%v) = %v, want %v", tt.err, got, tt.expected)
			}
		})
	}
}
