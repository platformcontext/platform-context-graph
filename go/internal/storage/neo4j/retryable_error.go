package neo4j

import "errors"

// neo4jCodeError is the structural interface for Neo4j driver errors that
// carry a server error code. This matches the driver's error type without
// importing the driver package, relying on Go's structural typing.
type neo4jCodeError interface {
	Neo4jCode() string
}

// retryableNeo4jCodes lists Neo4j error codes that are safe to retry in
// reducer materialization paths. Scoped narrowly to codes evidenced as
// transient under concurrent projector/reducer graph access.
//
// See: docs/docs/adrs/2026-04-16-cross-phase-entity-not-found-race.md
var retryableNeo4jCodes = map[string]bool{
	"Neo.ClientError.Statement.EntityNotFound":        true,
	"Neo.TransientError.Transaction.DeadlockDetected": true,
}

// neo4jRetryableError wraps a Neo4j error and implements
// reducer.RetryableError for codes evidenced as transient in concurrent
// projector/reducer access patterns.
type neo4jRetryableError struct {
	inner error
	code  string
}

func (e *neo4jRetryableError) Error() string   { return e.inner.Error() }
func (e *neo4jRetryableError) Unwrap() error   { return e.inner }
func (e *neo4jRetryableError) Retryable() bool { return true }

// WrapRetryableNeo4jError inspects err for known retryable Neo4j error codes.
// If the error (or any wrapped error in the chain) carries a code listed in
// retryableNeo4jCodes, the error is wrapped in a type implementing
// reducer.RetryableError. Otherwise the original error is returned unchanged.
func WrapRetryableNeo4jError(err error) error {
	if err == nil {
		return nil
	}
	var codeErr neo4jCodeError
	if !errors.As(err, &codeErr) {
		return err
	}
	code := codeErr.Neo4jCode()
	if retryableNeo4jCodes[code] {
		return &neo4jRetryableError{inner: err, code: code}
	}
	return err
}
