package neo4j

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"strings"
	"time"

	"go.opentelemetry.io/otel/metric"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

// RetryingExecutor wraps an Executor with retry logic for transient Neo4j
// errors such as deadlocks. Concurrent MERGE operations on shared nodes
// (Repository, Directory, Module) can trigger Neo4j deadlocks that resolve
// on retry.
type RetryingExecutor struct {
	Inner       Executor
	MaxRetries  int                    // default 3
	BaseDelay   time.Duration          // default 50ms, doubles per retry with jitter
	Instruments *telemetry.Instruments // optional; records retry counter
}

// Execute delegates to Inner, retrying on transient Neo4j errors (deadlocks,
// lock timeouts) with exponential backoff and jitter.
func (r *RetryingExecutor) Execute(ctx context.Context, stmt Statement) error {
	maxRetries := r.MaxRetries
	if maxRetries <= 0 {
		maxRetries = 3
	}
	baseDelay := r.BaseDelay
	if baseDelay <= 0 {
		baseDelay = 50 * time.Millisecond
	}

	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		lastErr = r.Inner.Execute(ctx, stmt)
		if lastErr == nil {
			return nil
		}

		if !isTransientNeo4jError(lastErr) {
			return lastErr
		}

		if attempt == maxRetries {
			break
		}

		// Record retry metric.
		if r.Instruments != nil && r.Instruments.Neo4jDeadlockRetries != nil {
			r.Instruments.Neo4jDeadlockRetries.Add(ctx, 1,
				metric.WithAttributes(telemetry.AttrWritePhase(string(stmt.Operation))))
		}

		// Exponential backoff with jitter: baseDelay * 2^attempt * (0.5..1.5)
		delay := baseDelay * time.Duration(1<<uint(attempt))
		jitter := time.Duration(float64(delay) * (0.5 + rand.Float64()))
		slog.Warn("neo4j transient error, retrying",
			"attempt", attempt+1,
			"max_retries", maxRetries,
			"delay", jitter.String(),
			"operation", string(stmt.Operation),
			"error", lastErr.Error(),
		)

		select {
		case <-ctx.Done():
			return fmt.Errorf("retry cancelled: %w", ctx.Err())
		case <-time.After(jitter):
		}
	}

	return fmt.Errorf("neo4j transient error after %d retries: %w", maxRetries, lastErr)
}

// isTransientNeo4jError returns true for Neo4j errors that are safe to retry:
// deadlocks, lock acquisition timeouts, and other transient failures.
func isTransientNeo4jError(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	return strings.Contains(msg, "TransientError") ||
		strings.Contains(msg, "DeadlockDetected") ||
		strings.Contains(msg, "LockClient") ||
		strings.Contains(msg, "lock acquisition")
}
