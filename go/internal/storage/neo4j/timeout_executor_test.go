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

type contextBlockingExecutor struct{}

func (contextBlockingExecutor) Execute(ctx context.Context, _ Statement) error {
	<-ctx.Done()
	return ctx.Err()
}
