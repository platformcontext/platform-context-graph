package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

type bootstrapDB interface {
	postgres.ExecQueryer
	Close() error
}

type graphDeps struct {
	writer graph.Writer
	close  func() error
}

type collectorDeps struct {
	source    collector.Source
	committer collector.Committer
}

type projectorDeps struct {
	workSource projector.ProjectorWorkSource
	factStore  projector.FactStore
	runner     projector.ProjectionRunner
	workSink   projector.ProjectorWorkSink
}

type openBootstrapDBFn func(context.Context, func(string) string) (bootstrapDB, error)
type applyBootstrapFn func(context.Context, bootstrapDB) error
type openGraphFn func(context.Context, func(string) string) (graphDeps, error)
type buildCollectorFn func(context.Context, bootstrapDB, func(string) string, trace.Tracer, *telemetry.Instruments, *slog.Logger) (collectorDeps, error)
type buildProjectorFn func(context.Context, bootstrapDB, graph.Writer, func(string) string, trace.Tracer, *telemetry.Instruments) (projectorDeps, error)

func main() {
	if err := run(
		context.Background(),
		os.Getenv,
		openBootstrapDB,
		applySchema,
		openBootstrapGraph,
		buildBootstrapCollector,
		buildBootstrapProjector,
	); err != nil {
		slog.Error("bootstrap-index failed", "error", err)
		os.Exit(1)
	}
}

func run(
	ctx context.Context,
	getenv func(string) string,
	openDBFn openBootstrapDBFn,
	schemaFn applyBootstrapFn,
	graphFn openGraphFn,
	collectorFn buildCollectorFn,
	projectorFn buildProjectorFn,
) (err error) {
	// Initialize telemetry
	bootstrap, err := telemetry.NewBootstrap("bootstrap-index")
	if err != nil {
		return fmt.Errorf("telemetry bootstrap: %w", err)
	}
	providers, err := telemetry.NewProviders(ctx, bootstrap)
	if err != nil {
		return fmt.Errorf("telemetry providers: %w", err)
	}
	defer func() {
		_ = providers.Shutdown(context.Background())
	}()

	logger := telemetry.NewLogger(bootstrap, "collector", "bootstrap-index")
	tracer := providers.TracerProvider.Tracer(telemetry.DefaultSignalName)
	meter := providers.MeterProvider.Meter(telemetry.DefaultSignalName)
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		return fmt.Errorf("telemetry instruments: %w", err)
	}

	memLimit := runtimecfg.ConfigureMemoryLimit(logger)
	if err := telemetry.RecordGOMEMLIMIT(meter, memLimit); err != nil {
		return fmt.Errorf("register gomemlimit gauge: %w", err)
	}
	logger.Info("starting bootstrap-index")

	db, err := openDBFn(ctx, getenv)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := db.Close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	if err = schemaFn(ctx, db); err != nil {
		return err
	}

	gd, err := graphFn(ctx, getenv)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := gd.close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	cd, err := collectorFn(ctx, db, getenv, tracer, instruments, logger)
	if err != nil {
		return err
	}

	if err = drainCollector(ctx, cd.source, cd.committer, tracer, instruments, logger); err != nil {
		return err
	}

	pd, err := projectorFn(ctx, db, gd.writer, getenv, tracer, instruments)
	if err != nil {
		return err
	}

	workers := projectionWorkerCount(getenv)
	logger.Info("starting bootstrap projection",
		slog.Int("workers", workers),
		telemetry.PhaseAttr(telemetry.PhaseProjection),
	)
	return drainProjector(ctx, pd.workSource, pd.factStore, pd.runner, pd.workSink, workers, tracer, instruments, logger)
}

// projectionWorkerCount returns the number of concurrent projection workers.
// Reads PCG_PROJECTION_WORKERS from env; defaults to NumCPU capped at 8.
func projectionWorkerCount(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_PROJECTION_WORKERS")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	n := runtime.NumCPU()
	if n > 8 {
		n = 8
	}
	if n < 1 {
		n = 1
	}
	return n
}

// drainCollector runs the collector source until no more work is available.
// Each cycle is wrapped in a collector.observe span with metric and log output
// so operators can trace collection throughput during bootstrap.
func drainCollector(
	ctx context.Context,
	source collector.Source,
	committer collector.Committer,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) error {
	var total int
	for {
		cycleStart := time.Now()

		var span trace.Span
		cycleCtx := ctx
		if tracer != nil {
			cycleCtx, span = tracer.Start(ctx, telemetry.SpanCollectorObserve,
				trace.WithAttributes(attribute.String("component", "bootstrap-index")),
			)
		}

		collected, ok, err := source.Next(cycleCtx)
		if err != nil {
			if span != nil {
				span.RecordError(err)
				span.End()
			}
			return fmt.Errorf("bootstrap collector: %w", err)
		}
		if !ok {
			if span != nil {
				span.End()
			}
			if logger != nil {
				logger.InfoContext(ctx, "bootstrap collection complete",
					slog.Int("scopes_collected", total),
					telemetry.PhaseAttr(telemetry.PhaseEmission),
				)
			}
			return nil
		}

		factCount := collected.FactCount
		if instruments != nil {
			instruments.FactsEmitted.Add(cycleCtx, int64(factCount), metric.WithAttributes(
				telemetry.AttrScopeID(collected.Scope.ScopeID),
				telemetry.AttrCollectorKind("bootstrap-index"),
			))
		}

		if err := committer.CommitScopeGeneration(
			cycleCtx,
			collected.Scope,
			collected.Generation,
			collected.Facts,
		); err != nil {
			if span != nil {
				span.RecordError(err)
				span.End()
			}
			if logger != nil {
				logger.ErrorContext(ctx, "bootstrap collector commit failed",
					slog.String("scope_id", collected.Scope.ScopeID),
					slog.Int("fact_count", factCount),
					slog.String("error", err.Error()),
					telemetry.PhaseAttr(telemetry.PhaseEmission),
					telemetry.FailureClassAttr("commit_failure"),
				)
			}
			return fmt.Errorf("bootstrap collector commit: %w", err)
		}

		duration := time.Since(cycleStart).Seconds()
		if instruments != nil {
			instruments.FactsCommitted.Add(cycleCtx, int64(factCount), metric.WithAttributes(
				telemetry.AttrScopeID(collected.Scope.ScopeID),
			))
			instruments.CollectorObserveDuration.Record(cycleCtx, duration, metric.WithAttributes(
				telemetry.AttrCollectorKind("bootstrap-index"),
			))
		}
		if logger != nil {
			logger.InfoContext(cycleCtx, "bootstrap scope collected",
				slog.String("scope_id", collected.Scope.ScopeID),
				slog.Int("fact_count", factCount),
				slog.Float64("duration_seconds", duration),
				telemetry.PhaseAttr(telemetry.PhaseEmission),
			)
		}
		if span != nil {
			span.SetAttributes(
				attribute.String("scope_id", collected.Scope.ScopeID),
				attribute.Int("fact_count", factCount),
			)
			span.End()
		}
		total++
	}
}

// drainProjector runs projection workers concurrently. Each worker claims
// work items from the queue, loads facts, projects, and acks independently.
//
// Concurrency model:
//   - N goroutine workers compete for work via workSource.Claim (Postgres
//     SELECT ... FOR UPDATE SKIP LOCKED ensures exactly-once delivery).
//   - On first error any worker cancels the shared context so siblings drain
//     promptly; all errors are collected and returned via errors.Join.
//   - An atomic counter tracks completed items for structured log output.
//
// Tuning: set PCG_PROJECTION_WORKERS to control parallelism. Default is
// min(NumCPU, 8). Monitor pcg_dp_projector_run_duration_seconds and
// pcg_dp_queue_claim_duration_seconds{queue=projector} to identify whether
// the bottleneck is CPU (increase workers) or I/O (tune Postgres connections).
func drainProjector(
	ctx context.Context,
	workSource projector.ProjectorWorkSource,
	factStore projector.FactStore,
	runner projector.ProjectionRunner,
	workSink projector.ProjectorWorkSink,
	workers int,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) error {
	if workers <= 1 {
		return drainProjectorSequential(ctx, workSource, factStore, runner, workSink, tracer, instruments, logger)
	}

	overallStart := time.Now()
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	var (
		mu        sync.Mutex
		errs      []error
		wg        sync.WaitGroup
		completed atomic.Int64
	)

	for i := 0; i < workers; i++ {
		workerID := i
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				if ctx.Err() != nil {
					return
				}

				if err := drainProjectorWorkItem(
					ctx, workSource, factStore, runner, workSink,
					workerID, &completed, tracer, instruments, logger,
				); err != nil {
					if errors.Is(err, errProjectorDrained) {
						return
					}
					mu.Lock()
					errs = append(errs, err)
					mu.Unlock()
					cancel()
					return
				}
			}
		}()
	}

	wg.Wait()

	totalCompleted := completed.Load()
	if logger != nil {
		logger.InfoContext(ctx, "bootstrap projection complete",
			slog.Int64("items_projected", totalCompleted),
			slog.Int("workers", workers),
			slog.Float64("total_duration_seconds", time.Since(overallStart).Seconds()),
			telemetry.PhaseAttr(telemetry.PhaseProjection),
		)
	}
	return errors.Join(errs...)
}

// errProjectorDrained is a sentinel indicating the work queue is empty.
var errProjectorDrained = errors.New("projector queue drained")

// drainProjectorWorkItem processes a single projection work item with full
// OTEL tracing, metric recording, and structured logging.
func drainProjectorWorkItem(
	ctx context.Context,
	workSource projector.ProjectorWorkSource,
	factStore projector.FactStore,
	runner projector.ProjectionRunner,
	workSink projector.ProjectorWorkSink,
	workerID int,
	completed *atomic.Int64,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) error {
	// Claim
	claimStart := time.Now()
	work, ok, err := workSource.Claim(ctx)
	if err != nil {
		return fmt.Errorf("bootstrap projector claim (worker %d): %w", workerID, err)
	}
	if instruments != nil {
		instruments.QueueClaimDuration.Record(ctx, time.Since(claimStart).Seconds(), metric.WithAttributes(
			attribute.String("queue", "projector"),
		))
	}
	if !ok {
		return errProjectorDrained
	}

	// Start span for the full project cycle
	itemStart := time.Now()
	itemCtx := ctx
	var span trace.Span
	if tracer != nil {
		itemCtx, span = tracer.Start(ctx, telemetry.SpanProjectorRun,
			trace.WithAttributes(
				attribute.String("scope_id", work.Scope.ScopeID),
				attribute.String("generation_id", work.Generation.GenerationID),
				attribute.Int("worker_id", workerID),
			),
		)
	}

	// Load facts
	factsForGeneration, loadErr := factStore.LoadFacts(itemCtx, work)
	if loadErr != nil {
		recordBootstrapProjectionResult(itemCtx, work, workerID, itemStart, "failed", 0, loadErr, span, instruments, logger)
		return fmt.Errorf("bootstrap projector load facts (worker %d): %w", workerID, loadErr)
	}

	// Project
	result, projectErr := runner.Project(itemCtx, work.Scope, work.Generation, factsForGeneration)
	if projectErr != nil {
		recordBootstrapProjectionResult(itemCtx, work, workerID, itemStart, "failed", len(factsForGeneration), projectErr, span, instruments, logger)
		return fmt.Errorf("bootstrap projector project (worker %d): %w", workerID, projectErr)
	}

	// Ack
	if ackErr := workSink.Ack(itemCtx, work, result); ackErr != nil {
		recordBootstrapProjectionResult(itemCtx, work, workerID, itemStart, "failed", len(factsForGeneration), ackErr, span, instruments, logger)
		return fmt.Errorf("bootstrap projector ack (worker %d): %w", workerID, ackErr)
	}

	completed.Add(1)
	recordBootstrapProjectionResult(itemCtx, work, workerID, itemStart, "succeeded", len(factsForGeneration), nil, span, instruments, logger)
	return nil
}

// recordBootstrapProjectionResult records metrics and logs for a single
// projection work item, matching the pattern in projector.Service.
func recordBootstrapProjectionResult(
	ctx context.Context,
	work projector.ScopeGenerationWork,
	workerID int,
	start time.Time,
	status string,
	factCount int,
	err error,
	span trace.Span,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) {
	duration := time.Since(start).Seconds()

	if instruments != nil {
		instruments.ProjectorRunDuration.Record(ctx, duration, metric.WithAttributes(
			telemetry.AttrScopeID(work.Scope.ScopeID),
		))
		instruments.ProjectionsCompleted.Add(ctx, 1, metric.WithAttributes(
			telemetry.AttrScopeID(work.Scope.ScopeID),
			attribute.String("status", status),
		))
	}

	if span != nil {
		span.SetAttributes(
			attribute.Int("fact_count", factCount),
			attribute.String("status", status),
		)
		if err != nil {
			span.RecordError(err)
		}
		span.End()
	}

	if logger != nil {
		scopeAttrs := telemetry.ScopeAttrs(work.Scope.ScopeID, work.Generation.GenerationID, work.Scope.SourceSystem)
		logAttrs := make([]any, 0, len(scopeAttrs)+5)
		for _, a := range scopeAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs,
			slog.Int("worker_id", workerID),
			slog.String("status", status),
			slog.Int("fact_count", factCount),
			slog.Float64("duration_seconds", duration),
			telemetry.PhaseAttr(telemetry.PhaseProjection),
		)
		if err != nil {
			logAttrs = append(logAttrs, slog.String("error", err.Error()))
			logAttrs = append(logAttrs, telemetry.FailureClassAttr("projection_failure"))
			logger.ErrorContext(ctx, "bootstrap projection failed", logAttrs...)
		} else {
			logger.InfoContext(ctx, "bootstrap projection succeeded", logAttrs...)
		}
	}
}

// drainProjectorSequential is the single-worker fallback. It uses the same
// per-item instrumentation as the concurrent path for consistent telemetry.
func drainProjectorSequential(
	ctx context.Context,
	workSource projector.ProjectorWorkSource,
	factStore projector.FactStore,
	runner projector.ProjectionRunner,
	workSink projector.ProjectorWorkSink,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) error {
	var completed atomic.Int64
	overallStart := time.Now()
	for {
		err := drainProjectorWorkItem(
			ctx, workSource, factStore, runner, workSink,
			0, &completed, tracer, instruments, logger,
		)
		if err != nil {
			if errors.Is(err, errProjectorDrained) {
				if logger != nil {
					logger.InfoContext(ctx, "bootstrap projection complete",
						slog.Int64("items_projected", completed.Load()),
						slog.Int("workers", 1),
						slog.Float64("total_duration_seconds", time.Since(overallStart).Seconds()),
						telemetry.PhaseAttr(telemetry.PhaseProjection),
					)
				}
				return nil
			}
			return err
		}
	}
}

// bootstrapSQLDB wraps a *sql.DB so it satisfies both bootstrapDB (Close) and
// postgres.ExecQueryer (QueryContext returns postgres.Rows, not *sql.Rows).
type bootstrapSQLDB struct {
	postgres.SQLDB
	raw *sql.DB
}

func (b *bootstrapSQLDB) Close() error { return b.raw.Close() }

func openBootstrapDB(ctx context.Context, getenv func(string) string) (bootstrapDB, error) {
	db, err := runtimecfg.OpenPostgres(ctx, getenv)
	if err != nil {
		return nil, err
	}
	return &bootstrapSQLDB{SQLDB: postgres.SQLDB{DB: db}, raw: db}, nil
}

func applySchema(ctx context.Context, db bootstrapDB) error {
	return postgres.ApplyBootstrap(ctx, db)
}

func openBootstrapGraph(ctx context.Context, getenv func(string) string) (graphDeps, error) {
	writer, closer, err := openBootstrapGraphWriter(ctx, getenv)
	if err != nil {
		return graphDeps{}, err
	}
	return graphDeps{writer: writer, close: closer.Close}, nil
}
