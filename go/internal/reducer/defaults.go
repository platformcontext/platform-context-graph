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

	// CodeCallEdgeWriter writes canonical CALLS edges from reducer-owned parser
	// follow-ups.
	CodeCallEdgeWriter SharedProjectionEdgeWriter

	// SQLRelationshipEdgeWriter writes canonical SQL relationship edges
	// (REFERENCES_TABLE, HAS_COLUMN, TRIGGERS) from reducer-owned SQL entity
	// metadata.
	SQLRelationshipEdgeWriter SharedProjectionEdgeWriter

	// InheritanceEdgeWriter writes canonical INHERITS edges from reducer-owned
	// parser entity bases metadata.
	InheritanceEdgeWriter SharedProjectionEdgeWriter

	// CanonicalNodeChecker checks whether canonical code entity nodes exist in
	// the graph. Optional; nil disables the pre-flight check.
	CanonicalNodeChecker CanonicalNodeChecker

	// Cross-repo relationship resolution adapters. All optional; nil disables
	// cross-repo resolution during deployment_mapping reduction.
	EvidenceFactLoader EvidenceFactLoader
	AssertionLoader    AssertionLoader
	ResolutionPersister ResolutionPersister

	// RepoDependencyEdgeWriter writes cross-repo dependency edges resolved
	// from evidence facts. Optional; nil disables cross-repo edge writes.
	RepoDependencyEdgeWriter SharedProjectionEdgeWriter

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

	return NewRuntime(registry)
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
				FactLoader:   handlers.FactLoader,
				Materializer: handlers.WorkloadMaterializer,
			}
		case DomainCodeCallMaterialization:
			def.Handler = CodeCallMaterializationHandler{
				FactLoader:           handlers.FactLoader,
				EdgeWriter:           handlers.CodeCallEdgeWriter,
				CanonicalNodeChecker: handlers.CanonicalNodeChecker,
			}
		case DomainSemanticEntityMaterialization:
			def.Handler = SemanticEntityMaterializationHandler{
				FactLoader: handlers.FactLoader,
				Writer:     handlers.SemanticEntityWriter,
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
