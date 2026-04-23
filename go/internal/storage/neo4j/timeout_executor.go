package neo4j

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// TimeoutExecutor bounds individual graph write statements with a child
// context. A zero timeout preserves the caller's context unchanged.
type TimeoutExecutor struct {
	Inner   Executor
	Timeout time.Duration
}

// Execute forwards the statement with an optional deadline.
func (e TimeoutExecutor) Execute(ctx context.Context, statement Statement) error {
	if e.Inner == nil {
		return fmt.Errorf("inner executor is required")
	}
	if e.Timeout <= 0 {
		return e.Inner.Execute(ctx, statement)
	}

	execCtx, cancel := context.WithTimeout(ctx, e.Timeout)
	defer cancel()

	err := e.Inner.Execute(execCtx, statement)
	if errors.Is(execCtx.Err(), context.DeadlineExceeded) {
		return fmt.Errorf("neo4j execute timed out after %s: %w", e.Timeout, context.DeadlineExceeded)
	}
	return err
}

// ExecuteGroup forwards grouped statements with an optional deadline when the
// wrapped executor supports atomic grouped writes.
func (e TimeoutExecutor) ExecuteGroup(ctx context.Context, statements []Statement) error {
	if e.Inner == nil {
		return fmt.Errorf("inner executor is required")
	}
	ge, ok := e.Inner.(GroupExecutor)
	if !ok {
		return fmt.Errorf("inner executor does not support ExecuteGroup")
	}
	if e.Timeout <= 0 {
		return ge.ExecuteGroup(ctx, statements)
	}

	execCtx, cancel := context.WithTimeout(ctx, e.Timeout)
	defer cancel()

	err := ge.ExecuteGroup(execCtx, statements)
	if errors.Is(execCtx.Err(), context.DeadlineExceeded) {
		return fmt.Errorf("neo4j execute group timed out after %s: %w", e.Timeout, context.DeadlineExceeded)
	}
	return err
}
