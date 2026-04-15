package reducer

import (
	"context"
	"fmt"
)

// CypherExecutor executes one parameterised Cypher statement against Neo4j.
// This is the reducer-local interface — adapters bridge it to the storage
// layer's neo4j.Executor.
type CypherExecutor interface {
	ExecuteCypher(ctx context.Context, cypher string, params map[string]any) error
}

// DefaultMaterializerBatchSize is the default batch size for UNWIND operations.
const DefaultMaterializerBatchSize = 500

// MaterializeResult holds counts from one materialization pass.
type MaterializeResult struct {
	WorkloadsWritten            int
	InstancesWritten            int
	DeploymentSourcesWritten    int
	RuntimePlatformsWritten     int
	RepoDependenciesWritten     int
	WorkloadDependenciesWritten int
}

// WorkloadMaterializer converts projection results into canonical Neo4j graph
// writes. It is the Go equivalent of Python's materialize_workloads orchestrator.
type WorkloadMaterializer struct {
	executor  CypherExecutor
	BatchSize int
}

// NewWorkloadMaterializer returns a WorkloadMaterializer backed by the given
// CypherExecutor.
func NewWorkloadMaterializer(executor CypherExecutor) *WorkloadMaterializer {
	return &WorkloadMaterializer{executor: executor}
}

// batchSize returns the configured batch size or DefaultMaterializerBatchSize if zero.
func (m *WorkloadMaterializer) batchSize() int {
	if m.BatchSize <= 0 {
		return DefaultMaterializerBatchSize
	}
	return m.BatchSize
}

// executeBatched splits rows into chunks and executes the given Cypher query with UNWIND.
func (m *WorkloadMaterializer) executeBatched(ctx context.Context, cypher string, rows []map[string]any) error {
	batchSize := m.batchSize()
	for i := 0; i < len(rows); i += batchSize {
		end := i + batchSize
		if end > len(rows) {
			end = len(rows)
		}
		chunk := rows[i:end]
		if err := m.executor.ExecuteCypher(ctx, cypher, map[string]any{"rows": chunk}); err != nil {
			return err
		}
	}
	return nil
}

// Materialize writes all canonical workload, instance, deployment source, and
// runtime platform nodes and edges from a ProjectionResult.
func (m *WorkloadMaterializer) Materialize(
	ctx context.Context,
	projection *ProjectionResult,
) (MaterializeResult, error) {
	total := len(projection.WorkloadRows) +
		len(projection.InstanceRows) +
		len(projection.DeploymentSourceRows) +
		len(projection.RuntimePlatformRows)

	if total == 0 {
		return MaterializeResult{}, nil
	}
	if m.executor == nil {
		return MaterializeResult{}, fmt.Errorf("workload materializer executor is required")
	}

	var result MaterializeResult

	// Batch workloads
	if len(projection.WorkloadRows) > 0 {
		rows := make([]map[string]any, len(projection.WorkloadRows))
		for i, row := range projection.WorkloadRows {
			rows[i] = map[string]any{
				"repo_id":         row.RepoID,
				"workload_id":     row.WorkloadID,
				"workload_name":   row.WorkloadName,
				"workload_kind":   row.WorkloadKind,
				"evidence_source": EvidenceSourceWorkloads,
			}
		}
		if err := m.executeBatched(ctx, batchWorkloadUpsertCypher, rows); err != nil {
			return result, fmt.Errorf("write workloads: %w", err)
		}
		result.WorkloadsWritten = len(projection.WorkloadRows)
	}

	// Batch instances
	if len(projection.InstanceRows) > 0 {
		rows := make([]map[string]any, len(projection.InstanceRows))
		for i, row := range projection.InstanceRows {
			rows[i] = map[string]any{
				"workload_id":     row.WorkloadID,
				"instance_id":     row.InstanceID,
				"workload_name":   row.WorkloadName,
				"workload_kind":   row.WorkloadKind,
				"environment":     row.Environment,
				"repo_id":         row.RepoID,
				"evidence_source": EvidenceSourceWorkloads,
			}
		}
		if err := m.executeBatched(ctx, batchWorkloadInstanceUpsertCypher, rows); err != nil {
			return result, fmt.Errorf("write instances: %w", err)
		}
		result.InstancesWritten = len(projection.InstanceRows)
	}

	// Batch deployment sources
	if len(projection.DeploymentSourceRows) > 0 {
		rows := make([]map[string]any, len(projection.DeploymentSourceRows))
		for i, row := range projection.DeploymentSourceRows {
			rows[i] = map[string]any{
				"instance_id":        row.InstanceID,
				"deployment_repo_id": row.DeploymentRepoID,
				"evidence_source":    EvidenceSourceWorkloads,
			}
		}
		if err := m.executeBatched(ctx, batchDeploymentSourceUpsertCypher, rows); err != nil {
			return result, fmt.Errorf("write deployment sources: %w", err)
		}
		result.DeploymentSourcesWritten = len(projection.DeploymentSourceRows)
	}

	// Batch runtime platforms
	if len(projection.RuntimePlatformRows) > 0 {
		rows := make([]map[string]any, len(projection.RuntimePlatformRows))
		for i, row := range projection.RuntimePlatformRows {
			rows[i] = map[string]any{
				"instance_id":       row.InstanceID,
				"platform_id":       row.PlatformID,
				"platform_name":     row.PlatformName,
				"platform_kind":     row.PlatformKind,
				"platform_provider": row.PlatformProvider,
				"environment":       row.Environment,
				"platform_region":   row.PlatformRegion,
				"platform_locator":  row.PlatformLocator,
				"evidence_source":   EvidenceSourceWorkloads,
			}
		}
		if err := m.executeBatched(ctx, batchRuntimePlatformUpsertCypher, rows); err != nil {
			return result, fmt.Errorf("write runtime platforms: %w", err)
		}
		result.RuntimePlatformsWritten = len(projection.RuntimePlatformRows)
	}

	return result, nil
}

// MaterializeDependencies writes repo and workload DEPENDS_ON edges.
func (m *WorkloadMaterializer) MaterializeDependencies(
	ctx context.Context,
	repoDeps []RepoDependencyRow,
	workloadDeps []WorkloadDependencyRow,
) (MaterializeResult, error) {
	total := len(repoDeps) + len(workloadDeps)
	if total == 0 {
		return MaterializeResult{}, nil
	}
	if m.executor == nil {
		return MaterializeResult{}, fmt.Errorf("workload materializer executor is required")
	}

	var result MaterializeResult

	// Batch repo dependencies
	if len(repoDeps) > 0 {
		rows := make([]map[string]any, len(repoDeps))
		for i, row := range repoDeps {
			rows[i] = map[string]any{
				"repo_id":         row.RepoID,
				"target_repo_id":  row.TargetRepoID,
				"evidence_source": EvidenceSourceWorkloads,
			}
		}
		if err := m.executeBatched(ctx, batchRepoDependencyUpsertCypher, rows); err != nil {
			return result, fmt.Errorf("write repo dependencies: %w", err)
		}
		result.RepoDependenciesWritten = len(repoDeps)
	}

	// Batch workload dependencies
	if len(workloadDeps) > 0 {
		rows := make([]map[string]any, len(workloadDeps))
		for i, row := range workloadDeps {
			rows[i] = map[string]any{
				"workload_id":        row.WorkloadID,
				"target_workload_id": row.TargetWorkloadID,
				"evidence_source":    EvidenceSourceWorkloads,
			}
		}
		if err := m.executeBatched(ctx, batchWorkloadDependencyUpsertCypher, rows); err != nil {
			return result, fmt.Errorf("write workload dependencies: %w", err)
		}
		result.WorkloadDependenciesWritten = len(workloadDeps)
	}

	return result, nil
}

// Canonical Cypher templates — duplicated from storage/neo4j/canonical.go to
// avoid a circular import. The reducer package owns domain logic; storage/neo4j
// owns the driver adapter. These strings are identical.
const (
	canonicalWorkloadUpsertCypher = `MATCH (repo:Repository {id: $repo_id})
MERGE (w:Workload {id: $workload_id})
SET w.type = 'workload',
    w.name = $workload_name,
    w.kind = $workload_kind,
    w.repo_id = $repo_id,
    w.evidence_source = $evidence_source
MERGE (repo)-[rel:DEFINES]->(w)
SET rel.confidence = 1.0,
    rel.reason = 'Repository defines workload',
    rel.evidence_source = $evidence_source`

	canonicalWorkloadInstanceUpsertCypher = `MATCH (w:Workload {id: $workload_id})
MERGE (i:WorkloadInstance {id: $instance_id})
SET i.type = 'workload_instance',
    i.name = $workload_name,
    i.kind = $workload_kind,
    i.environment = $environment,
    i.workload_id = $workload_id,
    i.repo_id = $repo_id,
    i.evidence_source = $evidence_source
MERGE (i)-[rel:INSTANCE_OF]->(w)
SET rel.confidence = 1.0,
    rel.reason = 'Workload instance belongs to workload',
    rel.evidence_source = $evidence_source`

	canonicalRuntimePlatformUpsertCypher = `MATCH (i:WorkloadInstance {id: $instance_id})
MERGE (p:Platform {id: $platform_id})
ON CREATE SET p.evidence_source = $evidence_source
SET p.type = 'platform',
    p.name = $platform_name,
    p.kind = $platform_kind,
    p.provider = $platform_provider,
    p.environment = $environment,
    p.region = $platform_region,
    p.locator = $platform_locator
MERGE (i)-[rel:RUNS_ON]->(p)
SET rel.confidence = 1.0,
    rel.reason = 'Workload instance runs on inferred platform',
    rel.evidence_source = $evidence_source`

	canonicalDeploymentSourceUpsertCypher = `MATCH (i:WorkloadInstance {id: $instance_id})
MATCH (deployment_repo:Repository {id: $deployment_repo_id})
MERGE (i)-[rel:DEPLOYMENT_SOURCE]->(deployment_repo)
SET rel.confidence = 0.98,
    rel.reason = 'Deployment manifests for workload instance live in deployment repository',
    rel.evidence_source = $evidence_source`

	canonicalRepoDependencyUpsertCypher = `MATCH (source_repo:Repository {id: $repo_id})
MATCH (target_repo:Repository {id: $target_repo_id})
MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)
SET rel.confidence = 0.9,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = $evidence_source`

	canonicalWorkloadDependencyUpsertCypher = `MATCH (source:Workload {id: $workload_id})
MATCH (target:Workload {id: $target_workload_id})
MERGE (source)-[rel:DEPENDS_ON]->(target)
SET rel.confidence = 0.9,
    rel.reason = 'Runtime services list declares workload dependency',
    rel.evidence_source = $evidence_source`
)

// Batched UNWIND Cypher templates for bulk operations.
const (
	batchWorkloadUpsertCypher = `UNWIND $rows AS row
MATCH (repo:Repository {id: row.repo_id})
MERGE (w:Workload {id: row.workload_id})
SET w.type = 'workload',
    w.name = row.workload_name,
    w.kind = row.workload_kind,
    w.repo_id = row.repo_id,
    w.evidence_source = row.evidence_source
MERGE (repo)-[rel:DEFINES]->(w)
SET rel.confidence = 1.0,
    rel.reason = 'Repository defines workload',
    rel.evidence_source = row.evidence_source`

	batchWorkloadInstanceUpsertCypher = `UNWIND $rows AS row
MATCH (w:Workload {id: row.workload_id})
MERGE (i:WorkloadInstance {id: row.instance_id})
SET i.type = 'workload_instance',
    i.name = row.workload_name,
    i.kind = row.workload_kind,
    i.environment = row.environment,
    i.workload_id = row.workload_id,
    i.repo_id = row.repo_id,
    i.evidence_source = row.evidence_source
MERGE (i)-[rel:INSTANCE_OF]->(w)
SET rel.confidence = 1.0,
    rel.reason = 'Workload instance belongs to workload',
    rel.evidence_source = row.evidence_source`

	batchDeploymentSourceUpsertCypher = `UNWIND $rows AS row
MATCH (i:WorkloadInstance {id: row.instance_id})
MATCH (deployment_repo:Repository {id: row.deployment_repo_id})
MERGE (i)-[rel:DEPLOYMENT_SOURCE]->(deployment_repo)
SET rel.confidence = 0.98,
    rel.reason = 'Deployment manifests for workload instance live in deployment repository',
    rel.evidence_source = row.evidence_source`

	batchRuntimePlatformUpsertCypher = `UNWIND $rows AS row
MATCH (i:WorkloadInstance {id: row.instance_id})
MERGE (p:Platform {id: row.platform_id})
ON CREATE SET p.evidence_source = row.evidence_source
SET p.type = 'platform',
    p.name = row.platform_name,
    p.kind = row.platform_kind,
    p.provider = row.platform_provider,
    p.environment = row.environment,
    p.region = row.platform_region,
    p.locator = row.platform_locator
MERGE (i)-[rel:RUNS_ON]->(p)
SET rel.confidence = 1.0,
    rel.reason = 'Workload instance runs on inferred platform',
    rel.evidence_source = row.evidence_source`

	batchRepoDependencyUpsertCypher = `UNWIND $rows AS row
MATCH (source_repo:Repository {id: row.repo_id})
MATCH (target_repo:Repository {id: row.target_repo_id})
MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)
SET rel.confidence = 0.9,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = row.evidence_source`

	batchWorkloadDependencyUpsertCypher = `UNWIND $rows AS row
MATCH (source:Workload {id: row.workload_id})
MATCH (target:Workload {id: row.target_workload_id})
MERGE (source)-[rel:DEPENDS_ON]->(target)
SET rel.confidence = 0.9,
    rel.reason = 'Runtime services list declares workload dependency',
    rel.evidence_source = row.evidence_source`
)
