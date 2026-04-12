package reducer

import (
	"context"
	"fmt"
)

const defaultBlockedReason = "canonical reducer backend is not implemented for this domain yet"

// DefaultHandlers captures the reducer-owned backend adapters available for the
// default domain catalog.
type DefaultHandlers struct {
	WorkloadIdentityWriter WorkloadIdentityWriter
}

// BlockedDomainError reports that a reducer domain is intentionally registered
// but not yet backed by a canonical write target.
type BlockedDomainError struct {
	Domain Domain
	Reason string
}

// Error returns the stable blocked-domain message.
func (e BlockedDomainError) Error() string {
	return fmt.Sprintf("reducer domain %q is blocked: %s", e.Domain, e.Reason)
}

// BlockedHandler is the explicit placeholder for domains whose canonical write
// targets are not yet implemented.
type BlockedHandler struct {
	Domain Domain
	Reason string
}

// Handle returns a stable blocked-domain error instead of a fake success.
func (h BlockedHandler) Handle(_ context.Context, intent Intent) (Result, error) {
	domain := h.Domain
	if domain == "" {
		domain = intent.Domain
	}

	reason := h.Reason
	if reason == "" {
		reason = defaultBlockedReason
	}

	return Result{}, BlockedDomainError{
		Domain: domain,
		Reason: reason,
	}
}

// NewDefaultRegistry constructs the canonical reducer catalog with one real
// proof domain and explicit blocked handlers for the remaining domains.
func NewDefaultRegistry(handlers DefaultHandlers) (Registry, error) {
	registry := NewRegistry()
	for _, def := range DefaultDomainDefinitions() {
		def.Handler = defaultHandlerForDomain(def.Domain, handlers)
		if err := registry.Register(def); err != nil {
			return Registry{}, err
		}
	}

	return registry, nil
}

// NewDefaultRuntime builds a reducer runtime from the default domain catalog.
//
// This is the additive seam for reducer main wiring: callers can replace the
// manual DefaultDomainDefinitions registration loop with one constructor call
// while keeping the surrounding service, queue, and polling setup unchanged.
func NewDefaultRuntime(handlers DefaultHandlers) (*Runtime, error) {
	registry, err := NewDefaultRegistry(handlers)
	if err != nil {
		return nil, err
	}

	return NewRuntime(registry)
}

func defaultHandlerForDomain(domain Domain, handlers DefaultHandlers) Handler {
	switch domain {
	case DomainWorkloadIdentity:
		return WorkloadIdentityHandler{
			Writer: handlers.WorkloadIdentityWriter,
		}
	default:
		return BlockedHandler{
			Domain: domain,
			Reason: defaultBlockedReason,
		}
	}
}
