package reducer

import (
	"context"
	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

// FactLoader loads fact envelopes for one scope generation.
type FactLoader interface {
	ListFacts(ctx context.Context, scopeID, generationID string) ([]facts.Envelope, error)
}

// ResolvedRelationshipLoader loads resolved repo relationships for one scope.
type ResolvedRelationshipLoader interface {
	GetResolvedRelationships(
		ctx context.Context,
		scopeID string,
	) ([]relationships.ResolvedRelationship, error)
}

// GenerationScopedResolvedRelationshipLoader can return resolved
// relationships for one exact scope generation, avoiding mixed active
// snapshots when multiple relationship generations exist for the same scope.
type GenerationScopedResolvedRelationshipLoader interface {
	GetResolvedRelationshipsForGeneration(
		ctx context.Context,
		scopeID string,
		generationID string,
	) ([]relationships.ResolvedRelationship, error)
}

// WorkloadProjectionInputLoader can provide already-correlated workload
// candidates and environment overlays for workload materialization.
type WorkloadProjectionInputLoader interface {
	LoadWorkloadProjectionInputs(
		ctx context.Context,
		intent Intent,
	) ([]WorkloadCandidate, map[string][]string, error)
}

// WorkloadMaterializationHandler reduces one workload materialization intent
// into canonical graph writes (workloads, instances, deployment sources,
// runtime platforms). It loads facts from the content store, extracts workload
// candidates, builds projection rows, and writes them to Neo4j.
type WorkloadMaterializationHandler struct {
	FactLoader     FactLoader
	ResolvedLoader ResolvedRelationshipLoader
	InputLoader    WorkloadProjectionInputLoader
	Materializer   *WorkloadMaterializer
}

// Handle executes the workload materialization reduction path.
func (h WorkloadMaterializationHandler) Handle(
	ctx context.Context,
	intent Intent,
) (Result, error) {
	if intent.Domain != DomainWorkloadMaterialization {
		return Result{}, fmt.Errorf(
			"workload materialization handler does not accept domain %q",
			intent.Domain,
		)
	}
	if h.FactLoader == nil {
		return Result{}, fmt.Errorf("workload materialization fact loader is required")
	}
	if h.Materializer == nil {
		return Result{}, fmt.Errorf("workload materialization materializer is required")
	}

	candidates, deploymentEnvironments, err := h.loadProjectionInputs(ctx, intent)
	if err != nil {
		return Result{}, err
	}
	if len(candidates) == 0 {
		return Result{
			IntentID:        intent.IntentID,
			Domain:          DomainWorkloadMaterialization,
			Status:          ResultStatusSucceeded,
			EvidenceSummary: "no workload candidates found",
		}, nil
	}

	projection := BuildProjectionRows(candidates, deploymentEnvironments)

	materializeResult, err := h.Materializer.Materialize(ctx, projection)
	if err != nil {
		return Result{}, fmt.Errorf("materialize workloads: %w", err)
	}

	totalWrites := materializeResult.WorkloadsWritten +
		materializeResult.InstancesWritten +
		materializeResult.DeploymentSourcesWritten +
		materializeResult.RuntimePlatformsWritten

	return Result{
		IntentID: intent.IntentID,
		Domain:   DomainWorkloadMaterialization,
		Status:   ResultStatusSucceeded,
		EvidenceSummary: fmt.Sprintf(
			"materialized %d workloads, %d instances, %d deployment sources, %d runtime platforms",
			materializeResult.WorkloadsWritten,
			materializeResult.InstancesWritten,
			materializeResult.DeploymentSourcesWritten,
			materializeResult.RuntimePlatformsWritten,
		),
		CanonicalWrites: totalWrites,
	}, nil
}

func (h WorkloadMaterializationHandler) loadProjectionInputs(
	ctx context.Context,
	intent Intent,
) ([]WorkloadCandidate, map[string][]string, error) {
	inputLoader := h.InputLoader
	if inputLoader == nil {
		inputLoader = CorrelatedWorkloadProjectionInputLoader{
			FactLoader:     h.FactLoader,
			ResolvedLoader: h.ResolvedLoader,
		}
	}
	candidates, deploymentEnvironments, err := inputLoader.LoadWorkloadProjectionInputs(ctx, intent)
	if err != nil {
		return nil, nil, fmt.Errorf("load workload projection inputs: %w", err)
	}
	return candidates, deploymentEnvironments, nil
}
