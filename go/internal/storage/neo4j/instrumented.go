package neo4j

import (
	"context"
	"time"

	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
)

// InstrumentedExecutor wraps a Neo4j Executor with OTEL tracing and metrics.
// Both Tracer and Instruments are optional; if nil, the wrapper passes through
// without instrumentation overhead.
type InstrumentedExecutor struct {
	Inner       Executor
	Tracer      trace.Tracer
	Instruments *telemetry.Instruments
}

// Execute executes a Neo4j statement with optional OTEL tracing and metrics.
//
// If Tracer is non-nil, creates a child span named "neo4j.execute" with
// attributes db.system=neo4j and db.operation=<statement.Operation>.
//
// If Instruments is non-nil, records the execution duration on the
// pcg_dp_neo4j_query_duration_seconds histogram with attribute operation=write.
//
// On error, sets span status to error if tracing is enabled, then returns
// the error unchanged.
func (i *InstrumentedExecutor) Execute(ctx context.Context, statement Statement) error {
	start := time.Now()

	// Start span if tracer is available
	var span trace.Span
	if i.Tracer != nil {
		ctx, span = i.Tracer.Start(ctx, "neo4j.execute",
			trace.WithAttributes(
				attribute.String("db.system", "neo4j"),
				attribute.String("db.operation", string(statement.Operation)),
			),
		)
		defer span.End()
	}

	// Execute the inner statement
	err := i.Inner.Execute(ctx, statement)

	// Record duration if instruments are available
	if i.Instruments != nil {
		duration := time.Since(start).Seconds()
		i.Instruments.Neo4jQueryDuration.Record(ctx, duration, metric.WithAttributes(
			attribute.String("operation", "write"),
		))
	}

	// Record batch size if this is a batch operation
	if i.Instruments != nil {
		if rows, ok := statement.Parameters["rows"]; ok {
			if rowSlice, ok := rows.([]map[string]any); ok {
				i.Instruments.Neo4jBatchSize.Record(ctx, float64(len(rowSlice)))
				i.Instruments.Neo4jBatchesExecuted.Add(ctx, 1, metric.WithAttributes(
					attribute.String("operation", string(statement.Operation)),
				))
			}
		}
	}

	// Set span status on error
	if err != nil && span != nil {
		span.SetStatus(codes.Error, err.Error())
	}

	return err
}

// ExecuteGroup forwards to Inner.ExecuteGroup when the inner executor
// implements GroupExecutor. Returns an error if it does not.
func (i *InstrumentedExecutor) ExecuteGroup(ctx context.Context, stmts []Statement) error {
	ge, ok := i.Inner.(GroupExecutor)
	if !ok {
		return fmt.Errorf("inner executor does not support ExecuteGroup")
	}

	start := time.Now()

	var span trace.Span
	if i.Tracer != nil {
		ctx, span = i.Tracer.Start(ctx, "neo4j.execute_group",
			trace.WithAttributes(
				attribute.String("db.system", "neo4j"),
				attribute.Int("db.statement_count", len(stmts)),
			),
		)
		defer span.End()
	}

	err := ge.ExecuteGroup(ctx, stmts)

	if i.Instruments != nil && i.Instruments.Neo4jQueryDuration != nil {
		duration := time.Since(start).Seconds()
		i.Instruments.Neo4jQueryDuration.Record(ctx, duration, metric.WithAttributes(
			attribute.String("operation", "write_group"),
		))
	}

	if err != nil && span != nil {
		span.SetStatus(codes.Error, err.Error())
	}

	return err
}
