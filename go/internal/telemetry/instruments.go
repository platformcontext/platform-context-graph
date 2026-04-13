// Package telemetry provides pre-registered OTEL metric instruments for the
// Go data plane.
package telemetry

import (
	"errors"
	"fmt"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

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

	inst.CanonicalWriteDuration, err = meter.Float64Histogram(
		"pcg_dp_canonical_write_duration_seconds",
		metric.WithDescription("Canonical graph write duration"),
		metric.WithUnit("s"),
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

	inst.Neo4jQueryDuration, err = meter.Float64Histogram(
		"pcg_dp_neo4j_query_duration_seconds",
		metric.WithDescription("Neo4j query duration"),
		metric.WithUnit("s"),
	)
	if err != nil {
		return nil, fmt.Errorf("register Neo4jQueryDuration histogram: %w", err)
	}

	return inst, nil
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
