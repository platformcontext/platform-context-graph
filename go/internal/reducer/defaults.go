package reducer

import (
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

// DefaultHandlers captures the reducer-owned backend adapters available for the
// default domain catalog.
type DefaultHandlers struct {
	WorkloadIdentityWriter        WorkloadIdentityWriter
	CloudAssetResolutionWriter    CloudAssetResolutionWriter
	PlatformMaterializationWriter PlatformMaterializationWriter

	// Neo4j-backed adapters for canonical graph writes.
	WorkloadMaterializer               *WorkloadMaterializer
	InfrastructurePlatformMaterializer *InfrastructurePlatformMaterializer
	SemanticEntityWriter               SemanticEntityWriter

	// FactLoader loads fact envelopes for workload and infrastructure
	// platform materialization.
	FactLoader FactLoader

	// CodeCallIntentWriter persists durable shared-intent rows for code-call
	// and Python metaclass materialization.
	CodeCallIntentWriter CodeCallIntentWriter

	// GraphProjectionPhasePublisher persists durable graph-readiness publications
	// for canonical and semantic node writers.
	GraphProjectionPhasePublisher GraphProjectionPhasePublisher

	// CodeCallEdgeWriter is retained for compatibility with older reducer tests
	// and wiring. Code-call materialization no longer uses it directly.
	CodeCallEdgeWriter SharedProjectionEdgeWriter

	// SQLRelationshipEdgeWriter writes canonical SQL relationship edges
	// (REFERENCES_TABLE, HAS_COLUMN, TRIGGERS) from reducer-owned SQL entity
	// metadata.
	SQLRelationshipEdgeWriter SharedProjectionEdgeWriter

	// InheritanceEdgeWriter writes canonical INHERITS, OVERRIDES, and ALIASES
	// edges from reducer-owned parser entity bases and trait adaptation
	// metadata.
	InheritanceEdgeWriter SharedProjectionEdgeWriter

	// Cross-repo relationship resolution adapters. All optional; nil disables
	// cross-repo resolution during deployment_mapping reduction.
	EvidenceFactLoader         EvidenceFactLoader
	AssertionLoader            AssertionLoader
	ResolutionPersister        ResolutionPersister
	ResolvedRelationshipLoader ResolvedRelationshipLoader

	// RepoDependencyEdgeWriter writes cross-repo dependency edges resolved
	// from evidence facts. Optional; nil disables cross-repo edge writes.
	RepoDependencyEdgeWriter SharedProjectionEdgeWriter

	// GenerationCheck reports whether an intent's generation is still current.
	// Nil disables the guard and lets all intents execute unconditionally.
	GenerationCheck GenerationFreshnessCheck

	// Tracer and Instruments for cross-repo resolution telemetry.
	Tracer      trace.Tracer
	Instruments *telemetry.Instruments
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

	rt, err := NewRuntime(registry)
	if err != nil {
		return nil, err
	}
	rt.GenerationCheck = handlers.GenerationCheck
	return rt, nil
}

func implementedDefaultDomainDefinitions(handlers DefaultHandlers) []DomainDefinition {
	definitions := make([]DomainDefinition, 0, len(DefaultDomainDefinitions()))
	for _, def := range DefaultDomainDefinitions() {
		switch def.Domain {
		case DomainWorkloadIdentity:
			def.Handler = WorkloadIdentityHandler{Writer: handlers.WorkloadIdentityWriter}
		case DomainCloudAssetResolution:
			def.Handler = CloudAssetResolutionHandler{Writer: handlers.CloudAssetResolutionWriter}
		case DomainDeploymentMapping:
			var crossRepoResolver *CrossRepoRelationshipHandler
			if handlers.EvidenceFactLoader != nil && handlers.RepoDependencyEdgeWriter != nil {
				crossRepoResolver = &CrossRepoRelationshipHandler{
					EvidenceLoader: handlers.EvidenceFactLoader,
					Assertions:     handlers.AssertionLoader,
					Persister:      handlers.ResolutionPersister,
					EdgeWriter:     handlers.RepoDependencyEdgeWriter,
					Tracer:         handlers.Tracer,
					Instruments:    handlers.Instruments,
				}
			}
			def.Handler = PlatformMaterializationHandler{
				Writer:                     handlers.PlatformMaterializationWriter,
				FactLoader:                 handlers.FactLoader,
				InfrastructureMaterializer: handlers.InfrastructurePlatformMaterializer,
				CrossRepoResolver:          crossRepoResolver,
			}
		case DomainWorkloadMaterialization:
			def.Handler = WorkloadMaterializationHandler{
				FactLoader:     handlers.FactLoader,
				ResolvedLoader: handlers.ResolvedRelationshipLoader,
				Materializer:   handlers.WorkloadMaterializer,
			}
		case DomainCodeCallMaterialization:
			def.Handler = CodeCallMaterializationHandler{
				FactLoader:   handlers.FactLoader,
				IntentWriter: handlers.CodeCallIntentWriter,
			}
		case DomainSemanticEntityMaterialization:
			def.Handler = SemanticEntityMaterializationHandler{
				FactLoader:     handlers.FactLoader,
				Writer:         handlers.SemanticEntityWriter,
				PhasePublisher: handlers.GraphProjectionPhasePublisher,
			}
		case DomainSQLRelationshipMaterialization:
			def.Handler = SQLRelationshipMaterializationHandler{
				FactLoader: handlers.FactLoader,
				EdgeWriter: handlers.SQLRelationshipEdgeWriter,
			}
		case DomainInheritanceMaterialization:
			def.Handler = InheritanceMaterializationHandler{
				FactLoader: handlers.FactLoader,
				EdgeWriter: handlers.InheritanceEdgeWriter,
			}
		default:
			continue
		}
		definitions = append(definitions, def)
	}

	return definitions
}
