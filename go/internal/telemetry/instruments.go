// Package telemetry provides pre-registered OTEL metric instruments for the
// Go data plane.
package telemetry

import (
	"context"
	"errors"
	"fmt"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

// QueueObserver provides queue depth and age readings for observable gauges.
type QueueObserver interface {
	// QueueDepths returns the current depth of each queue by status.
	// Keys: queue name -> status (pending, in_flight, retrying) -> count.
	QueueDepths(ctx context.Context) (map[string]map[string]int64, error)

	// QueueOldestAge returns the age in seconds of the oldest item per queue.
	QueueOldestAge(ctx context.Context) (map[string]float64, error)
}

// WorkerObserver provides active worker counts for observable gauges.
type WorkerObserver interface {
	// ActiveWorkers returns the current active count per worker pool.
	ActiveWorkers(ctx context.Context) (map[string]int64, error)
}

// Instruments holds all pre-registered OTEL metric instruments for the Go
// data plane. All instruments use the pcg_dp_ prefix to differentiate from
// Python pcg_ metrics.
type Instruments struct {
	// Counters track cumulative totals
	FactsEmitted              metric.Int64Counter
	FactsCommitted            metric.Int64Counter
	ProjectionsCompleted      metric.Int64Counter
	ReducerIntentsEnqueued    metric.Int64Counter
	ReducerExecutions         metric.Int64Counter
	CanonicalWrites           metric.Int64Counter
	SharedProjectionCycles    metric.Int64Counter

	// Histograms track distributions
	CollectorObserveDuration  metric.Float64Histogram
	ScopeAssignDuration       metric.Float64Histogram
	FactEmitDuration          metric.Float64Histogram
	ProjectorRunDuration      metric.Float64Histogram
	ProjectorStageDuration    metric.Float64Histogram
	ReducerRunDuration        metric.Float64Histogram
	CanonicalWriteDuration    metric.Float64Histogram
	QueueClaimDuration        metric.Float64Histogram
	PostgresQueryDuration     metric.Float64Histogram
	Neo4jQueryDuration        metric.Float64Histogram

	// Collector concurrency histograms and counters
	RepoSnapshotDuration  metric.Float64Histogram
	FileParseDuration     metric.Float64Histogram
	ReposSnapshotted      metric.Int64Counter
	FilesParsed           metric.Int64Counter

	// Streaming fact production metrics
	FactBatchesCommitted  metric.Int64Counter
	GenerationFactCount   metric.Float64Histogram
	ContentReReads        metric.Int64Counter
	ContentReReadSkips    metric.Int64Counter

	// Discovery skip counters — per-name breakdown of what discovery prunes
	DiscoveryDirsSkipped  metric.Int64Counter
	DiscoveryFilesSkipped metric.Int64Counter

	// Size-tiered scheduling metrics
	LargeRepoClassifications metric.Int64Counter
	LargeRepoSemaphoreWait   metric.Float64Histogram

	// Reducer batch claim metric
	BatchClaimSize metric.Int64Histogram

	// Neo4j batch write metrics
	Neo4jBatchSize       metric.Float64Histogram
	Neo4jBatchesExecuted metric.Int64Counter

	// Canonical projection metrics
	CanonicalNodesWritten      metric.Int64Counter
	CanonicalEdgesWritten      metric.Int64Counter
	CanonicalProjectionDuration metric.Float64Histogram
	CanonicalRetractDuration   metric.Float64Histogram
	CanonicalBatchSize         metric.Float64Histogram
	CanonicalPhaseDuration     metric.Float64Histogram

	// Neo4j transient error retry metrics
	Neo4jDeadlockRetries metric.Int64Counter

	// Cross-repo resolution metrics
	CrossRepoResolutionDuration metric.Float64Histogram
	CrossRepoEvidenceLoaded     metric.Int64Counter
	CrossRepoEdgesResolved      metric.Int64Counter

	// Pipeline overlap metric — how long collector and projector ran concurrently
	PipelineOverlapDuration metric.Float64Histogram

	// Observable gauges for autoscaling signals
	QueueDepth         metric.Int64ObservableGauge
	QueueOldestAge     metric.Float64ObservableGauge
	WorkerPoolActive   metric.Int64ObservableGauge
}

// NewInstruments creates and registers all OTEL metric instruments using the
// provided meter. Returns an error if the meter is nil or if any instrument
// registration fails.
func NewInstruments(meter metric.Meter) (*Instruments, error) {
	if meter == nil {
		return nil, errors.New("meter is required")
	}

	inst := &Instruments{}
	var err error

	// Register counters
	inst.FactsEmitted, err = meter.Int64Counter(
		"pcg_dp_facts_emitted_total",
		metric.WithDescription("Total facts emitted by collector"),
	)
	if err != nil {
		return nil, fmt.Errorf("register FactsEmitted counter: %w", err)
	}

	inst.FactsCommitted, err = meter.Int64Counter(
		"pcg_dp_facts_committed_total",
		metric.WithDescription("Total facts committed to store"),
	)
	if err != nil {
		return nil, fmt.Errorf("register FactsCommitted counter: %w", err)
	}

	inst.ProjectionsCompleted, err = meter.Int64Counter(
		"pcg_dp_projections_completed_total",
		metric.WithDescription("Total projection cycles completed"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ProjectionsCompleted counter: %w", err)
	}

	inst.ReducerIntentsEnqueued, err = meter.Int64Counter(
		"pcg_dp_reducer_intents_enqueued_total",
		metric.WithDescription("Total reducer intents enqueued"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ReducerIntentsEnqueued counter: %w", err)
	}

	inst.ReducerExecutions, err = meter.Int64Counter(
		"pcg_dp_reducer_executions_total",
		metric.WithDescription("Total reducer intent executions"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ReducerExecutions counter: %w", err)
	}

	inst.CanonicalWrites, err = meter.Int64Counter(
		"pcg_dp_canonical_writes_total",
		metric.WithDescription("Total canonical graph write batches"),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalWrites counter: %w", err)
	}

	inst.SharedProjectionCycles, err = meter.Int64Counter(
		"pcg_dp_shared_projection_cycles_total",
		metric.WithDescription("Total shared projection partition cycles"),
	)
	if err != nil {
		return nil, fmt.Errorf("register SharedProjectionCycles counter: %w", err)
	}

	// Register histograms with explicit bucket boundaries where specified
	collectorBuckets := []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60}
	inst.CollectorObserveDuration, err = meter.Float64Histogram(
		"pcg_dp_collector_observe_duration_seconds",
		metric.WithDescription("Collector observe cycle duration"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(collectorBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CollectorObserveDuration histogram: %w", err)
	}

	inst.ScopeAssignDuration, err = meter.Float64Histogram(
		"pcg_dp_scope_assign_duration_seconds",
		metric.WithDescription("Scope assignment duration"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ScopeAssignDuration histogram: %w", err)
	}

	inst.FactEmitDuration, err = meter.Float64Histogram(
		"pcg_dp_fact_emit_duration_seconds",
		metric.WithDescription("Fact emission duration"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, fmt.Errorf("register FactEmitDuration histogram: %w", err)
	}

	projectorBuckets := []float64{0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120}
	inst.ProjectorRunDuration, err = meter.Float64Histogram(
		"pcg_dp_projector_run_duration_seconds",
		metric.WithDescription("Projector run cycle duration"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(projectorBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register ProjectorRunDuration histogram: %w", err)
	}

	inst.ProjectorStageDuration, err = meter.Float64Histogram(
		"pcg_dp_projector_stage_duration_seconds",
		metric.WithDescription("Projector stage duration"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ProjectorStageDuration histogram: %w", err)
	}

	inst.ReducerRunDuration, err = meter.Float64Histogram(
		"pcg_dp_reducer_run_duration_seconds",
		metric.WithDescription("Reducer intent execution duration"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ReducerRunDuration histogram: %w", err)
	}

	canonicalWriteBuckets := []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60}
	inst.CanonicalWriteDuration, err = meter.Float64Histogram(
		"pcg_dp_canonical_write_duration_seconds",
		metric.WithDescription("Canonical graph write duration"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(canonicalWriteBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalWriteDuration histogram: %w", err)
	}

	inst.QueueClaimDuration, err = meter.Float64Histogram(
		"pcg_dp_queue_claim_duration_seconds",
		metric.WithDescription("Queue work item claim duration"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, fmt.Errorf("register QueueClaimDuration histogram: %w", err)
	}

	postgresBuckets := []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5}
	inst.PostgresQueryDuration, err = meter.Float64Histogram(
		"pcg_dp_postgres_query_duration_seconds",
		metric.WithDescription("Postgres query duration"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(postgresBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register PostgresQueryDuration histogram: %w", err)
	}

	neo4jQueryBuckets := []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10}
	inst.Neo4jQueryDuration, err = meter.Float64Histogram(
		"pcg_dp_neo4j_query_duration_seconds",
		metric.WithDescription("Neo4j query duration"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(neo4jQueryBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register Neo4jQueryDuration histogram: %w", err)
	}

	// Collector concurrency instruments
	repoSnapshotBuckets := []float64{0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300}
	inst.RepoSnapshotDuration, err = meter.Float64Histogram(
		"pcg_dp_repo_snapshot_duration_seconds",
		metric.WithDescription("Per-repository snapshot duration including discovery, parsing, and materialization"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(repoSnapshotBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register RepoSnapshotDuration histogram: %w", err)
	}

	fileParseBuckets := []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5}
	inst.FileParseDuration, err = meter.Float64Histogram(
		"pcg_dp_file_parse_duration_seconds",
		metric.WithDescription("Per-file parse duration"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(fileParseBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register FileParseDuration histogram: %w", err)
	}

	inst.ReposSnapshotted, err = meter.Int64Counter(
		"pcg_dp_repos_snapshotted_total",
		metric.WithDescription("Total repositories snapshotted by status"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ReposSnapshotted counter: %w", err)
	}

	inst.FilesParsed, err = meter.Int64Counter(
		"pcg_dp_files_parsed_total",
		metric.WithDescription("Total files parsed by status"),
	)
	if err != nil {
		return nil, fmt.Errorf("register FilesParsed counter: %w", err)
	}

	inst.FactBatchesCommitted, err = meter.Int64Counter(
		"pcg_dp_fact_batches_committed_total",
		metric.WithDescription("Total fact batches committed to Postgres during streaming ingestion"),
	)
	if err != nil {
		return nil, fmt.Errorf("register FactBatchesCommitted counter: %w", err)
	}

	// Use wide buckets for fact counts — repos range from 5 to 295k facts
	generationFactBuckets := []float64{10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000, 300000}
	inst.GenerationFactCount, err = meter.Float64Histogram(
		"pcg_dp_generation_fact_count",
		metric.WithDescription("Fact count per scope generation, for identifying outlier repos"),
		metric.WithExplicitBucketBoundaries(generationFactBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register GenerationFactCount histogram: %w", err)
	}

	inst.ContentReReads, err = meter.Int64Counter(
		"pcg_dp_content_rereads_total",
		metric.WithDescription("Total content file re-reads from disk during two-phase streaming"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ContentReReads counter: %w", err)
	}

	inst.ContentReReadSkips, err = meter.Int64Counter(
		"pcg_dp_content_reread_skips_total",
		metric.WithDescription("Content re-reads skipped due to missing file or read error"),
	)
	if err != nil {
		return nil, fmt.Errorf("register ContentReReadSkips counter: %w", err)
	}

	inst.DiscoveryDirsSkipped, err = meter.Int64Counter(
		"pcg_dp_discovery_dirs_skipped_total",
		metric.WithDescription("Directories pruned during file discovery, labeled by ignored directory name"),
	)
	if err != nil {
		return nil, fmt.Errorf("register DiscoveryDirsSkipped counter: %w", err)
	}

	inst.DiscoveryFilesSkipped, err = meter.Int64Counter(
		"pcg_dp_discovery_files_skipped_total",
		metric.WithDescription("Files skipped during file discovery, labeled by skip reason (extension or hidden)"),
	)
	if err != nil {
		return nil, fmt.Errorf("register DiscoveryFilesSkipped counter: %w", err)
	}

	inst.LargeRepoClassifications, err = meter.Int64Counter(
		"pcg_dp_large_repo_classifications_total",
		metric.WithDescription("Repositories classified by size tier (small or large)"),
	)
	if err != nil {
		return nil, fmt.Errorf("register LargeRepoClassifications counter: %w", err)
	}

	semWaitBuckets := []float64{0, 0.1, 0.5, 1, 5, 10, 30, 60, 120, 300}
	inst.LargeRepoSemaphoreWait, err = meter.Float64Histogram(
		"pcg_dp_large_repo_semaphore_wait_seconds",
		metric.WithDescription("Time spent waiting for the large-repo semaphore before snapshotting"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(semWaitBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register LargeRepoSemaphoreWait histogram: %w", err)
	}

	batchClaimBuckets := []float64{1, 4, 8, 16, 32, 64, 128}
	inst.BatchClaimSize, err = meter.Int64Histogram(
		"pcg_dp_reducer_batch_claim_size",
		metric.WithDescription("Number of work items claimed per batch claim call"),
		metric.WithExplicitBucketBoundaries(batchClaimBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register BatchClaimSize histogram: %w", err)
	}

	neo4jBatchBuckets := []float64{1, 10, 50, 100, 250, 500, 1000}
	inst.Neo4jBatchSize, err = meter.Float64Histogram(
		"pcg_dp_neo4j_batch_size",
		metric.WithDescription("Number of rows per Neo4j UNWIND batch execution"),
		metric.WithExplicitBucketBoundaries(neo4jBatchBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register Neo4jBatchSize histogram: %w", err)
	}

	inst.Neo4jBatchesExecuted, err = meter.Int64Counter(
		"pcg_dp_neo4j_batches_executed_total",
		metric.WithDescription("Total Neo4j UNWIND batch executions"),
	)
	if err != nil {
		return nil, fmt.Errorf("register Neo4jBatchesExecuted counter: %w", err)
	}

	inst.Neo4jDeadlockRetries, err = meter.Int64Counter(
		"pcg_dp_neo4j_deadlock_retries_total",
		metric.WithDescription("Total Neo4j transient error retries (deadlocks, lock timeouts)"),
	)
	if err != nil {
		return nil, fmt.Errorf("register Neo4jDeadlockRetries counter: %w", err)
	}

	// Canonical projection instruments
	inst.CanonicalNodesWritten, err = meter.Int64Counter(
		"pcg_dp_canonical_nodes_written_total",
		metric.WithDescription("Total canonical nodes written to Neo4j, labeled by node type"),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalNodesWritten counter: %w", err)
	}

	inst.CanonicalEdgesWritten, err = meter.Int64Counter(
		"pcg_dp_canonical_edges_written_total",
		metric.WithDescription("Total canonical edges written to Neo4j, labeled by edge type"),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalEdgesWritten counter: %w", err)
	}

	canonicalProjectionBuckets := []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60}
	inst.CanonicalProjectionDuration, err = meter.Float64Histogram(
		"pcg_dp_canonical_projection_duration_seconds",
		metric.WithDescription("Total canonical projection duration per repository"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(canonicalProjectionBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalProjectionDuration histogram: %w", err)
	}

	canonicalRetractBuckets := []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5}
	inst.CanonicalRetractDuration, err = meter.Float64Histogram(
		"pcg_dp_canonical_retract_duration_seconds",
		metric.WithDescription("Duration of canonical node retraction per repository"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(canonicalRetractBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalRetractDuration histogram: %w", err)
	}

	canonicalBatchBuckets := []float64{1, 10, 50, 100, 250, 500, 1000}
	inst.CanonicalBatchSize, err = meter.Float64Histogram(
		"pcg_dp_canonical_batch_size",
		metric.WithDescription("Rows per canonical UNWIND batch execution"),
		metric.WithExplicitBucketBoundaries(canonicalBatchBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalBatchSize histogram: %w", err)
	}

	canonicalPhaseBuckets := []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}
	inst.CanonicalPhaseDuration, err = meter.Float64Histogram(
		"pcg_dp_canonical_phase_duration_seconds",
		metric.WithDescription("Duration of each canonical write phase (repository, directories, files, entities, etc.)"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(canonicalPhaseBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CanonicalPhaseDuration histogram: %w", err)
	}

	// Cross-repo resolution instruments
	crossRepoBuckets := []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30}
	inst.CrossRepoResolutionDuration, err = meter.Float64Histogram(
		"pcg_dp_cross_repo_resolution_duration_seconds",
		metric.WithDescription("Duration of cross-repo relationship resolution per generation"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(crossRepoBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register CrossRepoResolutionDuration histogram: %w", err)
	}

	inst.CrossRepoEvidenceLoaded, err = meter.Int64Counter(
		"pcg_dp_cross_repo_evidence_loaded_total",
		metric.WithDescription("Total evidence facts loaded for cross-repo resolution"),
	)
	if err != nil {
		return nil, fmt.Errorf("register CrossRepoEvidenceLoaded counter: %w", err)
	}

	inst.CrossRepoEdgesResolved, err = meter.Int64Counter(
		"pcg_dp_cross_repo_edges_resolved_total",
		metric.WithDescription("Total dependency edges resolved from cross-repo evidence"),
	)
	if err != nil {
		return nil, fmt.Errorf("register CrossRepoEdgesResolved counter: %w", err)
	}

	pipelineOverlapBuckets := []float64{1, 5, 10, 30, 60, 120, 300, 600, 1800}
	inst.PipelineOverlapDuration, err = meter.Float64Histogram(
		"pcg_dp_pipeline_overlap_seconds",
		metric.WithDescription("Time both collector and projector ran concurrently during bootstrap"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(pipelineOverlapBuckets...),
	)
	if err != nil {
		return nil, fmt.Errorf("register PipelineOverlapDuration histogram: %w", err)
	}

	return inst, nil
}

// RegisterObservableGauges registers observable gauge instruments with their
// callback functions. This is separate from NewInstruments because the observer
// implementations may not be available at instrument creation time.
func RegisterObservableGauges(
	inst *Instruments,
	meter metric.Meter,
	queueObs QueueObserver,
	workerObs WorkerObserver,
) error {
	if inst == nil {
		return errors.New("instruments must not be nil")
	}
	if meter == nil {
		return errors.New("meter is required for observable gauges")
	}

	var err error

	if queueObs != nil {
		inst.QueueDepth, err = meter.Int64ObservableGauge(
			"pcg_dp_queue_depth",
			metric.WithDescription("Current queue depth by queue and status"),
			metric.WithInt64Callback(func(ctx context.Context, o metric.Int64Observer) error {
				depths, err := queueObs.QueueDepths(ctx)
				if err != nil {
					return err
				}
				for queue, statuses := range depths {
					for status, count := range statuses {
						o.Observe(count,
							metric.WithAttributes(
								attribute.String("queue", queue),
								attribute.String("status", status),
							),
						)
					}
				}
				return nil
			}),
		)
		if err != nil {
			return fmt.Errorf("register QueueDepth gauge: %w", err)
		}

		inst.QueueOldestAge, err = meter.Float64ObservableGauge(
			"pcg_dp_queue_oldest_age_seconds",
			metric.WithDescription("Age of oldest queue item in seconds"),
			metric.WithUnit("s"),
			metric.WithFloat64Callback(func(ctx context.Context, o metric.Float64Observer) error {
				ages, err := queueObs.QueueOldestAge(ctx)
				if err != nil {
					return err
				}
				for queue, age := range ages {
					o.Observe(age,
						metric.WithAttributes(
							attribute.String("queue", queue),
						),
					)
				}
				return nil
			}),
		)
		if err != nil {
			return fmt.Errorf("register QueueOldestAge gauge: %w", err)
		}
	}

	if workerObs != nil {
		inst.WorkerPoolActive, err = meter.Int64ObservableGauge(
			"pcg_dp_worker_pool_active",
			metric.WithDescription("Current active worker count per pool"),
			metric.WithInt64Callback(func(ctx context.Context, o metric.Int64Observer) error {
				counts, err := workerObs.ActiveWorkers(ctx)
				if err != nil {
					return err
				}
				for pool, count := range counts {
					o.Observe(count,
						metric.WithAttributes(
							attribute.String("pool", pool),
						),
					)
				}
				return nil
			}),
		)
		if err != nil {
			return fmt.Errorf("register WorkerPoolActive gauge: %w", err)
		}
	}

	return nil
}

// AttrScopeID returns a scope_id attribute for metric recording.
func AttrScopeID(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionScopeID, v)
}

// AttrScopeKind returns a scope_kind attribute for metric recording.
func AttrScopeKind(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionScopeKind, v)
}

// AttrSourceSystem returns a source_system attribute for metric recording.
func AttrSourceSystem(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionSourceSystem, v)
}

// AttrGenerationID returns a generation_id attribute for metric recording.
func AttrGenerationID(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionGenerationID, v)
}

// AttrCollectorKind returns a collector_kind attribute for metric recording.
func AttrCollectorKind(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionCollectorKind, v)
}

// AttrDomain returns a domain attribute for metric recording.
func AttrDomain(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionDomain, v)
}

// AttrPartitionKey returns a partition_key attribute for metric recording.
func AttrPartitionKey(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionPartitionKey, v)
}

// AttrRepoSizeTier returns a repo_size_tier attribute for metric recording.
func AttrRepoSizeTier(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionRepoSizeTier, v)
}

// AttrSkipReason returns a skip_reason attribute for discovery skip metrics.
func AttrSkipReason(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionSkipReason, v)
}

// AttrNodeType returns a node_type attribute for canonical write metrics.
func AttrNodeType(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionNodeType, v)
}

// AttrEdgeType returns an edge_type attribute for canonical write metrics.
func AttrEdgeType(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionEdgeType, v)
}

// AttrWritePhase returns a write_phase attribute for canonical phase metrics.
func AttrWritePhase(v string) attribute.KeyValue {
	return attribute.String(MetricDimensionWritePhase, v)
}

// RecordGOMEMLIMIT registers and records the applied GOMEMLIMIT as a gauge.
// Call once at startup after instruments and memlimit are configured.
func RecordGOMEMLIMIT(meter metric.Meter, limitBytes int64) error {
	if meter == nil {
		return nil
	}
	_, err := meter.Int64ObservableGauge(
		"pcg_dp_gomemlimit_bytes",
		metric.WithDescription("Configured GOMEMLIMIT in bytes"),
		metric.WithUnit("By"),
		metric.WithInt64Callback(func(_ context.Context, o metric.Int64Observer) error {
			o.Observe(limitBytes)
			return nil
		}),
	)
	return err
}
