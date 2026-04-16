package neo4j

import (
	"errors"
	"fmt"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// fakeNeo4jError simulates a Neo4j driver error carrying a server error code.
type fakeNeo4jError struct {
	code    string
	message string
}

func (e *fakeNeo4jError) Error() string     { return e.message }
func (e *fakeNeo4jError) Neo4jCode() string { return e.code }

func TestWrapRetryableNeo4jError(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name          string
		err           error
		wantRetryable bool
		wantWrapped   bool // true when WrapRetryableNeo4jError should return a different error
		wantMessage   string
	}{
		{
			name:          "nil error returns nil",
			err:           nil,
			wantRetryable: false,
			wantWrapped:   false,
		},
		{
			name:          "EntityNotFound is retryable",
			err:           &fakeNeo4jError{code: "Neo.ClientError.Statement.EntityNotFound", message: "Unable to load NODE 4:abc:123"},
			wantRetryable: true,
			wantWrapped:   true,
			wantMessage:   "Unable to load NODE 4:abc:123",
		},
		{
			name:          "DeadlockDetected is retryable",
			err:           &fakeNeo4jError{code: "Neo.TransientError.Transaction.DeadlockDetected", message: "deadlock detected"},
			wantRetryable: true,
			wantWrapped:   true,
			wantMessage:   "deadlock detected",
		},
		{
			name:          "other Neo4j code is not retryable",
			err:           &fakeNeo4jError{code: "Neo.ClientError.Schema.ConstraintValidationFailed", message: "constraint failed"},
			wantRetryable: false,
			wantWrapped:   false,
			wantMessage:   "constraint failed",
		},
		{
			name:          "plain error without Neo4jCode is not retryable",
			err:           errors.New("connection reset"),
			wantRetryable: false,
			wantWrapped:   false,
			wantMessage:   "connection reset",
		},
		{
			name:          "wrapped EntityNotFound preserves retryable through chain",
			err:           fmt.Errorf("write semantic entities: %w", &fakeNeo4jError{code: "Neo.ClientError.Statement.EntityNotFound", message: "node gone"}),
			wantRetryable: true,
			wantWrapped:   true,
			wantMessage:   "node gone",
		},
		{
			name:          "wrapped DeadlockDetected preserves retryable through chain",
			err:           fmt.Errorf("retract edges: %w", &fakeNeo4jError{code: "Neo.TransientError.Transaction.DeadlockDetected", message: "deadlock"}),
			wantRetryable: true,
			wantWrapped:   true,
			wantMessage:   "deadlock",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			result := WrapRetryableNeo4jError(tt.err)

			if tt.err == nil {
				assert.Nil(t, result)
				return
			}

			if !tt.wantWrapped {
				// Error should be returned unchanged
				assert.Same(t, tt.err, result, "non-retryable error should be returned as-is")
				assert.False(t, reducer.IsRetryable(result), "non-retryable error should not satisfy IsRetryable")
				return
			}

			// Error should be wrapped as retryable
			require.NotNil(t, result)
			assert.True(t, reducer.IsRetryable(result), "wrapped error should satisfy reducer.IsRetryable()")
			assert.Contains(t, result.Error(), tt.wantMessage, "error message should be preserved")

			// Original error should be accessible via Unwrap
			var codeErr neo4jCodeError
			assert.True(t, errors.As(result, &codeErr), "original Neo4j error should be reachable via errors.As")
		})
	}
}

func TestNeo4jRetryableErrorImplementsInterface(t *testing.T) {
	t.Parallel()

	inner := &fakeNeo4jError{
		code:    "Neo.ClientError.Statement.EntityNotFound",
		message: "node gone",
	}
	wrapped := WrapRetryableNeo4jError(inner)

	// Verify it implements reducer.RetryableError
	var retryable reducer.RetryableError
	require.True(t, errors.As(wrapped, &retryable))
	assert.True(t, retryable.Retryable())

	// Verify Unwrap chain preserves the original
	assert.True(t, errors.Is(wrapped, inner))
}
