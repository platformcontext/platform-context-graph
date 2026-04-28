package reducer

import (
	"context"
	"fmt"
	"log/slog"
	"time"

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

// RepoScopeIdentity holds the active scope and generation for a repository.
type RepoScopeIdentity struct {
	ScopeID      string
	GenerationID string
}

// DeploymentRepoScopeResolver resolves repository graph IDs to their active
// scope and generation identities, enabling cross-repo fact loading during
// workload materialization.
type DeploymentRepoScopeResolver interface {
	ResolveRepoActiveGenerations(ctx context.Context, repoIDs []string) (map[string]RepoScopeIdentity, error)
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
	FactLoader                   FactLoader
	ResolvedLoader               ResolvedRelationshipLoader
	InputLoader                  WorkloadProjectionInputLoader
	Materializer                 *WorkloadMaterializer
	DependencyLookup             WorkloadDependencyGraphLookup
	WorkloadDependencyEdgeWriter SharedProjectionEdgeWriter
	PhasePublisher               GraphProjectionPhasePublisher
}

// workloadMaterializationTiming keeps success-path stage timings comparable
// with SQL and semantic reducer logs without changing handler behavior.
type workloadMaterializationTiming struct {
	loadInputsDuration      time.Duration
	buildProjectionDuration time.Duration
	graphWriteDuration      time.Duration
	dependencyReconcile     time.Duration
	dependencyRetract       time.Duration
	dependencyWrite         time.Duration
	phasePublishDuration    time.Duration
	totalDuration           time.Duration
}

// Handle executes the workload materialization reduction path.
func (h WorkloadMaterializationHandler) Handle(
	ctx context.Context,
	intent Intent,
) (Result, error) {
	totalStarted := time.Now()
	var timing workloadMaterializationTiming

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

	loadStarted := time.Now()
	candidates, deploymentEnvironments, err := h.loadProjectionInputs(ctx, intent)
	timing.loadInputsDuration = time.Since(loadStarted)
	if err != nil {
		return Result{}, err
	}
	if len(candidates) == 0 {
		phaseStarted := time.Now()
		if err := publishIntentGraphPhase(
			ctx,
			h.PhasePublisher,
			intent,
			GraphProjectionKeyspaceServiceUID,
			GraphProjectionPhaseWorkloadMaterialization,
			time.Now().UTC(),
		); err != nil {
			return Result{}, err
		}
		timing.phasePublishDuration = time.Since(phaseStarted)
		timing.totalDuration = time.Since(totalStarted)
		logWorkloadMaterializationCompleted(ctx, intent, candidates, nil, MaterializeResult{}, timing, 0, 0)
		return Result{
			IntentID:        intent.IntentID,
			Domain:          DomainWorkloadMaterialization,
			Status:          ResultStatusSucceeded,
			EvidenceSummary: "no workload candidates found",
		}, nil
	}

	buildStarted := time.Now()
	projection := BuildProjectionRows(candidates, deploymentEnvironments)
	timing.buildProjectionDuration = time.Since(buildStarted)

	graphStarted := time.Now()
	materializeResult, err := h.Materializer.Materialize(ctx, projection)
	timing.graphWriteDuration = time.Since(graphStarted)
	if err != nil {
		return Result{}, fmt.Errorf("materialize workloads: %w", err)
	}

	totalWrites := materializeResult.WorkloadsWritten +
		materializeResult.InstancesWritten +
		materializeResult.DeploymentSourcesWritten +
		materializeResult.RuntimePlatformsWritten

	dependencyRetractRows := 0
	dependencyWriteRows := 0
	if h.DependencyLookup != nil && h.WorkloadDependencyEdgeWriter != nil {
		reconcileStarted := time.Now()
		dependencyRows, retractRows, err := ReconcileWorkloadDependencyEdges(
			ctx,
			projection.RepoDescriptors,
			h.DependencyLookup,
		)
		timing.dependencyReconcile = time.Since(reconcileStarted)
		if err != nil {
			return Result{}, fmt.Errorf("reconcile workload dependencies: %w", err)
		}
		if len(retractRows) > 0 {
			retractStarted := time.Now()
			if err := h.WorkloadDependencyEdgeWriter.RetractEdges(
				ctx,
				DomainWorkloadDependency,
				retractRows,
				EvidenceSourceWorkloads,
			); err != nil {
				return Result{}, fmt.Errorf("retract workload dependencies: %w", err)
			}
			timing.dependencyRetract = time.Since(retractStarted)
			dependencyRetractRows = len(retractRows)
			totalWrites += len(retractRows)
		}
		if writeRows := BuildWorkloadDependencyIntentRowsFromEdges(dependencyRows); len(writeRows) > 0 {
			writeStarted := time.Now()
			if err := h.WorkloadDependencyEdgeWriter.WriteEdges(
				ctx,
				DomainWorkloadDependency,
				writeRows,
				EvidenceSourceWorkloads,
			); err != nil {
				return Result{}, fmt.Errorf("write workload dependencies: %w", err)
			}
			timing.dependencyWrite = time.Since(writeStarted)
			dependencyWriteRows = len(writeRows)
			totalWrites += len(writeRows)
		}
	}
	phaseStarted := time.Now()
	if err := publishIntentGraphPhase(
		ctx,
		h.PhasePublisher,
		intent,
		GraphProjectionKeyspaceServiceUID,
		GraphProjectionPhaseWorkloadMaterialization,
		time.Now().UTC(),
	); err != nil {
		return Result{}, err
	}
	timing.phasePublishDuration = time.Since(phaseStarted)
	timing.totalDuration = time.Since(totalStarted)
	logWorkloadMaterializationCompleted(
		ctx,
		intent,
		candidates,
		projection,
		materializeResult,
		timing,
		dependencyRetractRows,
		dependencyWriteRows,
	)

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

func logWorkloadMaterializationCompleted(
	ctx context.Context,
	intent Intent,
	candidates []WorkloadCandidate,
	projection *ProjectionResult,
	materializeResult MaterializeResult,
	timing workloadMaterializationTiming,
	dependencyRetractRows int,
	dependencyWriteRows int,
) {
	workloadRows := 0
	instanceRows := 0
	deploymentSourceRows := 0
	runtimePlatformRows := 0
	if projection != nil {
		workloadRows = len(projection.WorkloadRows)
		instanceRows = len(projection.InstanceRows)
		deploymentSourceRows = len(projection.DeploymentSourceRows)
		runtimePlatformRows = len(projection.RuntimePlatformRows)
	}

	slog.InfoContext(ctx, "workload materialization completed",
		slog.String("scope_id", intent.ScopeID),
		slog.String("generation_id", intent.GenerationID),
		slog.String("domain", string(DomainWorkloadMaterialization)),
		slog.Int("candidate_count", len(candidates)),
		slog.Int("workload_row_count", workloadRows),
		slog.Int("instance_row_count", instanceRows),
		slog.Int("deployment_source_row_count", deploymentSourceRows),
		slog.Int("runtime_platform_row_count", runtimePlatformRows),
		slog.Int("workloads_written", materializeResult.WorkloadsWritten),
		slog.Int("instances_written", materializeResult.InstancesWritten),
		slog.Int("deployment_sources_written", materializeResult.DeploymentSourcesWritten),
		slog.Int("runtime_platforms_written", materializeResult.RuntimePlatformsWritten),
		slog.Int("dependency_retract_row_count", dependencyRetractRows),
		slog.Int("dependency_write_row_count", dependencyWriteRows),
		slog.Float64("load_inputs_duration_seconds", timing.loadInputsDuration.Seconds()),
		slog.Float64("build_projection_duration_seconds", timing.buildProjectionDuration.Seconds()),
		slog.Float64("graph_write_duration_seconds", timing.graphWriteDuration.Seconds()),
		slog.Float64("workload_graph_write_duration_seconds", materializeResult.WorkloadWriteDuration.Seconds()),
		slog.Float64("instance_graph_write_duration_seconds", materializeResult.InstanceWriteDuration.Seconds()),
		slog.Float64("deployment_source_graph_write_duration_seconds", materializeResult.DeploymentSourceDuration.Seconds()),
		slog.Float64("runtime_platform_graph_write_duration_seconds", materializeResult.RuntimePlatformDuration.Seconds()),
		slog.Float64("dependency_reconcile_duration_seconds", timing.dependencyReconcile.Seconds()),
		slog.Float64("dependency_retract_duration_seconds", timing.dependencyRetract.Seconds()),
		slog.Float64("dependency_write_duration_seconds", timing.dependencyWrite.Seconds()),
		slog.Float64("phase_publish_duration_seconds", timing.phasePublishDuration.Seconds()),
		slog.Float64("total_duration_seconds", timing.totalDuration.Seconds()),
	)
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
