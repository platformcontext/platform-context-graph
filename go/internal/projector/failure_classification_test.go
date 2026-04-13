package projector

import (
	"context"
	"errors"
	"fmt"
	"net"
	"testing"
)

func TestClassifyNeo4jTransientError(t *testing.T) {
	t.Parallel()

	exc := neo4jLikeError{code: "Neo.TransientError.Transaction.DeadlockDetected"}
	result := ClassifyFailure(exc, "project_facts")

	if result.FailureStage != "project_facts" {
		t.Errorf("stage = %q, want project_facts", result.FailureStage)
	}
	if result.FailureClass != FailureClassDependencyUnavailable {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassDependencyUnavailable)
	}
	if result.RetryDisposition != RetryDispositionRetryable {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionRetryable)
	}
	if result.RetryAfterSeconds == 0 {
		t.Error("retry_after_seconds should be non-zero for Neo4j transient errors")
	}
	if result.ErrorClass != "neo4jLikeError" {
		t.Errorf("error_class = %q, want neo4jLikeError", result.ErrorClass)
	}
	want := "neo__transient_error__transaction__deadlock_detected"
	if result.FailureCode != want {
		t.Errorf("failure_code = %q, want %q", result.FailureCode, want)
	}
}

func TestClassifyTimeoutError(t *testing.T) {
	t.Parallel()

	exc := context.DeadlineExceeded
	result := ClassifyFailure(exc, "project_workloads")

	if result.FailureClass != FailureClassTimeout {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassTimeout)
	}
	if result.RetryDisposition != RetryDispositionRetryable {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionRetryable)
	}
	if result.FailureStage != "project_workloads" {
		t.Errorf("stage = %q, want project_workloads", result.FailureStage)
	}
}

func TestClassifyContextCanceledAsTimeout(t *testing.T) {
	t.Parallel()

	result := ClassifyFailure(context.Canceled, "load_facts")

	if result.FailureClass != FailureClassTimeout {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassTimeout)
	}
	if result.RetryDisposition != RetryDispositionRetryable {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionRetryable)
	}
}

func TestClassifyInputValidationError(t *testing.T) {
	t.Parallel()

	result := ClassifyFailure(NewInputValidationError("bad scope_id"), "project_work_item")

	if result.FailureClass != FailureClassInputInvalid {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassInputInvalid)
	}
	if result.RetryDisposition != RetryDispositionNonRetryable {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionNonRetryable)
	}
}

func TestClassifyConnectionError(t *testing.T) {
	t.Parallel()

	exc := &net.OpError{Op: "dial", Net: "tcp", Err: errors.New("connection refused")}
	result := ClassifyFailure(exc, "project_facts")

	if result.FailureClass != FailureClassDependencyUnavailable {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassDependencyUnavailable)
	}
	if result.RetryDisposition != RetryDispositionRetryable {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionRetryable)
	}
}

func TestClassifyResourceExhaustedError(t *testing.T) {
	t.Parallel()

	result := ClassifyFailure(NewResourceExhaustedError("OOM"), "project_entity_batches")

	if result.FailureClass != FailureClassResourceExhausted {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassResourceExhausted)
	}
	if result.RetryDisposition != RetryDispositionManualReview {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionManualReview)
	}
}

func TestClassifyUnknownErrorAsProjectionBug(t *testing.T) {
	t.Parallel()

	result := ClassifyFailure(errors.New("something unexpected"), "project_relationships")

	if result.FailureClass != FailureClassProjectionBug {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassProjectionBug)
	}
	if result.RetryDisposition != RetryDispositionManualReview {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionManualReview)
	}
}

func TestClassifyUnwrapsStageError(t *testing.T) {
	t.Parallel()

	inner := context.DeadlineExceeded
	wrapped := NewStageError("project_platforms", inner)
	result := ClassifyFailure(wrapped, "project_work_item")

	// Should use the stage from the StageError, not the caller's stage.
	if result.FailureStage != "project_platforms" {
		t.Errorf("stage = %q, want project_platforms", result.FailureStage)
	}
	if result.FailureClass != FailureClassTimeout {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassTimeout)
	}
}

func TestClassifyWrappedNeo4jTransient(t *testing.T) {
	t.Parallel()

	inner := neo4jLikeError{code: "Neo.TransientError.General.DatabaseUnavailable"}
	wrapped := fmt.Errorf("projector stage failed: %w", inner)
	result := ClassifyFailure(wrapped, "project_facts")

	if result.FailureClass != FailureClassDependencyUnavailable {
		t.Errorf("class = %q, want %q", result.FailureClass, FailureClassDependencyUnavailable)
	}
	if result.RetryDisposition != RetryDispositionRetryable {
		t.Errorf("disposition = %q, want %q", result.RetryDisposition, RetryDispositionRetryable)
	}
}

func TestFailureCodeNormalization(t *testing.T) {
	t.Parallel()

	code := normalizeNeo4jCode("Neo.TransientError.Transaction.DeadlockDetected")
	want := "neo__transient_error__transaction__deadlock_detected"
	if code != want {
		t.Errorf("code = %q, want %q", code, want)
	}
}

func TestFailureCodeForPlainError(t *testing.T) {
	t.Parallel()

	code := failureCode(errors.New("oops"))
	if code != "errors_error_string" {
		t.Errorf("code = %q, want errors_error_string", code)
	}
}

// -- test helpers --

// neo4jLikeError simulates a Neo4j driver error with a server error code.
type neo4jLikeError struct {
	code string
}

func (e neo4jLikeError) Error() string {
	return fmt.Sprintf("neo4j error: %s", e.code)
}

// Neo4jCode implements the Neo4jCodeError interface.
func (e neo4jLikeError) Neo4jCode() string {
	return e.code
}
