package projector

import "errors"

// RetryableError marks projector failures that should re-enter the durable
// queue instead of becoming terminal on the first failure.
type RetryableError interface {
	error
	Retryable() bool
}

// IsRetryable reports whether the supplied error explicitly opts into bounded
// retry behavior.
func IsRetryable(err error) bool {
	var retryable RetryableError
	if !errors.As(err, &retryable) {
		return false
	}

	return retryable.Retryable()
}
