package reducer

import "slices"

// DefaultHandlers captures the reducer-owned backend adapters available for the
// default domain catalog.
type DefaultHandlers struct {
	WorkloadIdentityWriter WorkloadIdentityWriter
}

// NewDefaultRegistry constructs the canonical reducer catalog for the domains
// implemented by the current rewrite slice.
func NewDefaultRegistry(handlers DefaultHandlers) (Registry, error) {
	registry := NewRegistry()
	for _, def := range implementedDefaultDomainDefinitions(handlers) {
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

func implementedDefaultDomainDefinitions(handlers DefaultHandlers) []DomainDefinition {
	for _, def := range DefaultDomainDefinitions() {
		if def.Domain != DomainWorkloadIdentity {
			continue
		}
		def.Handler = WorkloadIdentityHandler{Writer: handlers.WorkloadIdentityWriter}
		return []DomainDefinition{def}
	}

	return slices.Clip([]DomainDefinition{})
}
