package neo4j

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestTimeoutExecutorCancelsLongRunningExecute(t *testing.T) {
	t.Parallel()

	executor := TimeoutExecutor{
		Inner:   contextBlockingExecutor{},
		Timeout: 10 * time.Millisecond,
	}

	err := executor.Execute(context.Background(), Statement{Cypher: "RETURN 1"})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Execute() error = %v, want deadline exceeded", err)
	}
}

func TestTimeoutExecutorZeroTimeoutPassesThrough(t *testing.T) {
	t.Parallel()

	inner := &recordingExecutor{}
	executor := TimeoutExecutor{
		Inner: inner,
	}

	err := executor.Execute(context.Background(), Statement{Cypher: "RETURN 1"})
	if err != nil {
		t.Fatalf("Execute() error = %v, want nil", err)
	}
	if got, want := len(inner.calls), 1; got != want {
		t.Fatalf("inner calls = %d, want %d", got, want)
	}
}

func TestTimeoutExecutorExecuteGroupPassesThrough(t *testing.T) {
	t.Parallel()

	inner := &timeoutGroupRecordingExecutor{}
	executor := TimeoutExecutor{Inner: inner}

	err := executor.ExecuteGroup(context.Background(), []Statement{{Cypher: "RETURN 1"}})
	if err != nil {
		t.Fatalf("ExecuteGroup() error = %v, want nil", err)
	}
	if inner.groupCalls != 1 {
		t.Fatalf("inner ExecuteGroup calls = %d, want 1", inner.groupCalls)
	}
}

func TestTimeoutExecutorExecuteGroupCancelsLongRunningGroup(t *testing.T) {
	t.Parallel()

	executor := TimeoutExecutor{
		Inner:   contextBlockingGroupExecutor{},
		Timeout: 10 * time.Millisecond,
	}

	err := executor.ExecuteGroup(context.Background(), []Statement{{Cypher: "RETURN 1"}})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("ExecuteGroup() error = %v, want deadline exceeded", err)
	}
}

func TestTimeoutExecutorExecuteGroupErrorsWithoutGroupExecutor(t *testing.T) {
	t.Parallel()

	executor := TimeoutExecutor{Inner: &recordingExecutor{}}

	err := executor.ExecuteGroup(context.Background(), []Statement{{Cypher: "RETURN 1"}})
	if err == nil {
		t.Fatal("ExecuteGroup() error = nil, want non-nil")
	}
	if got, want := err.Error(), "inner executor does not support ExecuteGroup"; got != want {
		t.Fatalf("ExecuteGroup() error = %q, want %q", got, want)
	}
}

type contextBlockingExecutor struct{}

func (contextBlockingExecutor) Execute(ctx context.Context, _ Statement) error {
	<-ctx.Done()
	return ctx.Err()
}

type contextBlockingGroupExecutor struct{}

func (contextBlockingGroupExecutor) Execute(ctx context.Context, _ Statement) error {
	<-ctx.Done()
	return ctx.Err()
}

func (contextBlockingGroupExecutor) ExecuteGroup(ctx context.Context, _ []Statement) error {
	<-ctx.Done()
	return ctx.Err()
}

type timeoutGroupRecordingExecutor struct {
	groupCalls int
}

func (e *timeoutGroupRecordingExecutor) Execute(context.Context, Statement) error {
	return nil
}

func (e *timeoutGroupRecordingExecutor) ExecuteGroup(context.Context, []Statement) error {
	e.groupCalls++
	return nil
}
