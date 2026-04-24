package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"runtime"
	"strconv"
	"strings"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const (
	ingesterCollectorPollInterval        = time.Second
	ingesterConnectionTimeout            = 10 * time.Second
	defaultNornicDBCanonicalWriteTimeout = 15 * time.Second
	defaultNornicDBPhaseGroupStatements  = 500
	defaultNornicDBEntityPhaseStatements = 25
	defaultNornicDBEntityBatchSize       = 100
	canonicalWriteTimeoutEnv             = "PCG_CANONICAL_WRITE_TIMEOUT"
	nornicDBCanonicalGroupedWritesEnv    = "PCG_NORNICDB_CANONICAL_GROUPED_WRITES"
	nornicDBPhaseGroupStatementsEnv      = "PCG_NORNICDB_PHASE_GROUP_STATEMENTS"
	nornicDBEntityPhaseStatementsEnv     = "PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS"
	nornicDBEntityBatchSizeEnv           = "PCG_NORNICDB_ENTITY_BATCH_SIZE"
)

// compositeRunner runs multiple Runner implementations concurrently.
// If any runner returns an error, it cancels all others and returns the first error.
type compositeRunner struct {
	runners []app.Runner
}

// Run starts all runners concurrently and returns the first error received.
func (c compositeRunner) Run(ctx context.Context) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	errc := make(chan error, len(c.runners))
	for _, r := range c.runners {
		go func(runner app.Runner) {
			errc <- runner.Run(ctx)
		}(r)
	}

	err := <-errc
	cancel()
	for i := 1; i < len(c.runners); i++ {
		<-errc
	}
	return err
}

func buildIngesterService(
	database postgres.ExecQueryer,
	canonicalWriter projector.CanonicalWriter,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (compositeRunner, error) {
	collectorSvc, err := buildIngesterCollectorService(database, getenv, getwd, environ, tracer, instruments, logger)
	if err != nil {
		return compositeRunner{}, fmt.Errorf("build ingester collector: %w", err)
	}

	projectorSvc, err := buildIngesterProjectorService(database, canonicalWriter, getenv, tracer, instruments, logger)
	if err != nil {
		return compositeRunner{}, fmt.Errorf("build ingester projector: %w", err)
	}

	return compositeRunner{runners: []app.Runner{collectorSvc, projectorSvc}}, nil
}

func buildIngesterCollectorService(
	database postgres.ExecQueryer,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (collector.Service, error) {
	config, err := collector.LoadRepoSyncConfig("ingester", getenv)
	if err != nil {
		return collector.Service{}, err
	}

	return collector.Service{
		Source: &collector.GitSource{
			Component: "ingester",
			Selector:  collector.NativeRepositorySelector{Config: config},
			Snapshotter: collector.NativeRepositorySnapshotter{
				ParseWorkers: config.ParseWorkers,
				Tracer:       tracer,
				Instruments:  instruments,
				Logger:       logger,
			},
			SnapshotWorkers:        config.SnapshotWorkers,
			LargeRepoThreshold:     config.LargeRepoThreshold,
			LargeRepoMaxConcurrent: config.LargeRepoMaxConcurrent,
			StreamBuffer:           config.StreamBuffer,
			Tracer:                 tracer,
			Instruments:            instruments,
			Logger:                 logger,
		},
		Committer:    postgres.NewIngestionStore(database),
		PollInterval: ingesterCollectorPollInterval,
		Tracer:       tracer,
		Instruments:  instruments,
		Logger:       logger,
	}, nil
}

func buildIngesterProjectorService(
	database postgres.ExecQueryer,
	canonicalWriter projector.CanonicalWriter,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (projector.Service, error) {
	projectorQueue := postgres.NewProjectorQueue(database, "ingester", 5*time.Minute)
	reducerQueue := reducerIntentWriterForProfile(getenv, postgres.NewReducerQueue(database, "ingester", time.Minute))
	retryInjector, err := loadIngesterRetryInjector(getenv)
	if err != nil {
		return projector.Service{}, err
	}
	retryPolicy, err := loadIngesterRetryPolicy(getenv)
	if err != nil {
		return projector.Service{}, err
	}
	projectorQueue.RetryDelay = retryPolicy.RetryDelay
	projectorQueue.MaxAttempts = retryPolicy.MaxAttempts

	svc := projector.Service{
		PollInterval:          time.Second,
		WorkSource:            projectorQueue,
		FactStore:             postgres.NewFactStore(database),
		Runner:                buildIngesterProjectorRuntime(database, canonicalWriter, reducerQueue, retryInjector, getenv, tracer, instruments),
		WorkSink:              projectorQueue,
		Heartbeater:           projectorQueue,
		HeartbeatInterval:     projectorHeartbeatInterval(projectorQueue.LeaseDuration),
		Tracer:                tracer,
		Instruments:           instruments,
		Logger:                logger,
		Workers:               projectorWorkerCount(getenv),
		FactCounter:           postgres.NewFactStore(database),
		LargeGenThreshold:     largeGenThreshold(getenv),
		LargeGenMaxConcurrent: largeGenMaxConcurrent(getenv),
	}
	svc.InitLargeGenSemaphore()
	return svc, nil
}

func projectorHeartbeatInterval(leaseDuration time.Duration) time.Duration {
	if leaseDuration <= 0 {
		return time.Minute
	}
	interval := leaseDuration / 3
	if interval <= 0 {
		return time.Second
	}
	if interval > time.Minute {
		return time.Minute
	}
	return interval
}

func projectorWorkerCount(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_PROJECTOR_WORKERS")); raw != "" {
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

func largeGenThreshold(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_LARGE_GEN_THRESHOLD")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	return 10000
}

func largeGenMaxConcurrent(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_LARGE_GEN_MAX_CONCURRENT")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	return 2
}

func buildIngesterProjectorRuntime(
	database postgres.ExecQueryer,
	canonicalWriter projector.CanonicalWriter,
	intentWriter projector.ReducerIntentWriter,
	retryInjector projector.RetryInjector,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) projector.Runtime {
	return projector.Runtime{
		CanonicalWriter:        canonicalWriter,
		ContentWriter:          postgres.NewContentWriter(database),
		IntentWriter:           intentWriter,
		PhasePublisher:         postgres.NewGraphProjectionPhaseStateStore(database),
		RepairQueue:            postgres.NewGraphProjectionPhaseRepairQueueStore(database),
		RetryInjector:          retryInjector,
		ContentBeforeCanonical: ingesterContentBeforeCanonical(getenv),
		Tracer:                 tracer,
		Instruments:            instruments,
	}
}

func openIngesterCanonicalWriter(
	parent context.Context,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) (projector.CanonicalWriter, io.Closer, error) {
	if writer, closer, ok := maybeLocalLightweightCanonicalWriter(getenv); ok {
		return writer, closer, nil
	}
	graphBackend, err := runtimecfg.LoadGraphBackend(getenv)
	if err != nil {
		return nil, nil, err
	}
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, err
	}

	rawExecutor := ingesterNeo4jExecutor{
		Driver:       driver,
		DatabaseName: cfg.DatabaseName,
		TxTimeout:    canonicalTransactionTimeout(graphBackend, getenv),
	}

	nornicDBGroupedWrites := false
	phaseGroupStatements := defaultNornicDBPhaseGroupStatements
	entityPhaseStatements := defaultNornicDBEntityPhaseStatements
	entityBatchSize := 0
	if graphBackend == runtimecfg.GraphBackendNornicDB {
		nornicDBGroupedWrites, err = nornicDBCanonicalGroupedWrites(getenv)
		if err != nil {
			return nil, nil, err
		}
		phaseGroupStatements, err = nornicDBPhaseGroupStatements(getenv)
		if err != nil {
			return nil, nil, err
		}
		entityPhaseStatements, err = nornicDBEntityPhaseGroupStatements(getenv)
		if err != nil {
			return nil, nil, err
		}
		entityBatchSize, err = nornicDBEntityBatchSize(getenv)
		if err != nil {
			return nil, nil, err
		}
		if nornicDBGroupedWrites {
			slog.Warn("NornicDB canonical grouped writes enabled for conformance",
				"graph_backend", string(graphBackend),
				"grouped_writes", true,
				"env_var", nornicDBCanonicalGroupedWritesEnv)
		}
	}

	writer := sourceneo4j.NewCanonicalNodeWriter(
		canonicalExecutorForGraphBackend(
			rawExecutor,
			graphBackend,
			nornicDBCanonicalWriteTimeout(getenv),
			nornicDBGroupedWrites,
			phaseGroupStatements,
			entityPhaseStatements,
			tracer,
			instruments,
		),
		neo4jBatchSize(getenv),
		instruments,
	)
	if entityBatchSize > 0 {
		writer = writer.WithEntityBatchSize(entityBatchSize)
	}

	return writer, ingesterNeo4jDriverCloser{Driver: driver}, nil
}

func canonicalExecutorForGraphBackend(
	rawExecutor sourceneo4j.Executor,
	graphBackend runtimecfg.GraphBackend,
	nornicDBTimeout time.Duration,
	nornicDBGroupedWrites bool,
	nornicDBPhaseGroupStatements int,
	nornicDBEntityPhaseStatements int,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) sourceneo4j.Executor {
	instrumented := &sourceneo4j.InstrumentedExecutor{
		Inner: &sourceneo4j.RetryingExecutor{
			Inner:       rawExecutor,
			MaxRetries:  3,
			Instruments: instruments,
		},
		Tracer:      tracer,
		Instruments: instruments,
	}
	if graphBackend == runtimecfg.GraphBackendNornicDB {
		bounded := sourceneo4j.TimeoutExecutor{
			Inner:   instrumented,
			Timeout: nornicDBTimeout,
		}
		if nornicDBGroupedWrites {
			return bounded
		}
		return nornicDBPhaseGroupExecutor{
			inner:               bounded,
			maxStatements:       nornicDBPhaseGroupStatements,
			entityMaxStatements: nornicDBEntityPhaseStatements,
		}
	}
	return instrumented
}

type nornicDBPhaseGroupExecutor struct {
	inner               sourceneo4j.Executor
	maxStatements       int
	entityMaxStatements int
}

func (e nornicDBPhaseGroupExecutor) Execute(ctx context.Context, stmt sourceneo4j.Statement) error {
	if e.inner == nil {
		return nil
	}
	return e.inner.Execute(ctx, sanitizedStatement(stmt))
}

func (e nornicDBPhaseGroupExecutor) ExecutePhaseGroup(ctx context.Context, stmts []sourceneo4j.Statement) error {
	if len(stmts) == 0 || e.inner == nil {
		return nil
	}
	if ge, ok := e.inner.(sourceneo4j.GroupExecutor); ok {
		if statementPhase(stmts) == "entities" {
			return e.executeEntityPhaseGroup(ctx, ge, stmts)
		}
		return e.executeGroupedChunks(ctx, ge, stmts, e.phaseGroupStatementLimit(stmts))
	}
	for _, stmt := range stmts {
		if err := e.inner.Execute(ctx, sanitizedStatement(stmt)); err != nil {
			return err
		}
	}
	return nil
}

func (e nornicDBPhaseGroupExecutor) executeEntityPhaseGroup(
	ctx context.Context,
	ge sourceneo4j.GroupExecutor,
	stmts []sourceneo4j.Statement,
) error {
	grouped := make([]sourceneo4j.Statement, 0, len(stmts))
	flushGrouped := func() error {
		if len(grouped) == 0 {
			return nil
		}
		err := e.executeGroupedChunks(ctx, ge, grouped, e.phaseGroupStatementLimit(grouped))
		grouped = grouped[:0]
		return err
	}

	for i, stmt := range stmts {
		if statementPhaseGroupMode(stmt) == "execute_only" {
			if err := flushGrouped(); err != nil {
				return err
			}
			statementStart := time.Now()
			statementSummary := summarizePhaseGroupChunk([]sourceneo4j.Statement{stmt})
			if err := e.inner.Execute(ctx, sanitizedStatement(stmt)); err != nil {
				return fmt.Errorf(
					"phase-group singleton statement %d/%d (phase=%s, duration=%s, first_statement=%q): %w",
					i+1,
					len(stmts),
					statementPhase(stmts),
					time.Since(statementStart),
					statementSummary,
					err,
				)
			}
			slog.Info(
				"nornicdb phase-group singleton completed",
				"statement_index", i+1,
				"statement_count", len(stmts),
				"phase", statementPhase(stmts),
				"duration_s", time.Since(statementStart).Seconds(),
			)
			continue
		}
		grouped = append(grouped, stmt)
	}

	return flushGrouped()
}

func (e nornicDBPhaseGroupExecutor) executeGroupedChunks(
	ctx context.Context,
	ge sourceneo4j.GroupExecutor,
	stmts []sourceneo4j.Statement,
	maxStatements int,
) error {
	totalChunks := (len(stmts) + maxStatements - 1) / maxStatements
	for start := 0; start < len(stmts); start += maxStatements {
		end := start + maxStatements
		if end > len(stmts) {
			end = len(stmts)
		}
		chunkIndex := (start / maxStatements) + 1
		chunkStart := time.Now()
		chunk := stmts[start:end]
		statementSummary := summarizePhaseGroupChunk(chunk)
		err := ge.ExecuteGroup(ctx, sanitizedPhaseGroupChunk(chunk))
		chunkDuration := time.Since(chunkStart)
		if err != nil {
			return fmt.Errorf(
				"phase-group chunk %d/%d (statements %d-%d of %d, size=%d, duration=%s, first_statement=%q): %w",
				chunkIndex,
				totalChunks,
				start+1,
				end,
				len(stmts),
				end-start,
				chunkDuration,
				statementSummary,
				err,
			)
		}
		slog.Info(
			"nornicdb phase-group chunk completed",
			"chunk_index", chunkIndex,
			"chunk_count", totalChunks,
			"statement_start", start+1,
			"statement_end", end,
			"statement_count", end-start,
			"duration_s", chunkDuration.Seconds(),
		)
	}
	return nil
}

func (e nornicDBPhaseGroupExecutor) phaseGroupStatementLimit(stmts []sourceneo4j.Statement) int {
	if statementPhase(stmts) == "entities" {
		if e.entityMaxStatements > 0 {
			return e.entityMaxStatements
		}
		return defaultNornicDBEntityPhaseStatements
	}
	if e.maxStatements > 0 {
		return e.maxStatements
	}
	return defaultNornicDBPhaseGroupStatements
}

func statementPhase(stmts []sourceneo4j.Statement) string {
	if len(stmts) == 0 {
		return ""
	}
	phase, _ := stmts[0].Parameters["_pcg_phase"].(string)
	return strings.TrimSpace(phase)
}

func statementPhaseGroupMode(stmt sourceneo4j.Statement) string {
	mode, _ := stmt.Parameters["_pcg_phase_group_mode"].(string)
	return strings.TrimSpace(mode)
}

func summarizePhaseGroupChunk(stmts []sourceneo4j.Statement) string {
	if len(stmts) == 0 {
		return ""
	}
	if summary, ok := stmts[0].Parameters["_pcg_statement_summary"].(string); ok && strings.TrimSpace(summary) != "" {
		return summary
	}
	return summarizePhaseGroupStatement(stmts[0].Cypher)
}

func sanitizedPhaseGroupChunk(stmts []sourceneo4j.Statement) []sourceneo4j.Statement {
	sanitized := make([]sourceneo4j.Statement, len(stmts))
	for i, stmt := range stmts {
		sanitized[i] = sanitizedStatement(stmt)
	}
	return sanitized
}

func sanitizedStatement(stmt sourceneo4j.Statement) sourceneo4j.Statement {
	stmt.Parameters = sanitizedStatementParameters(stmt.Parameters)
	return stmt
}

func sanitizedStatementParameters(params map[string]any) map[string]any {
	if len(params) == 0 {
		return params
	}

	hasDiagnostics := false
	for key := range params {
		if strings.HasPrefix(key, "_") {
			hasDiagnostics = true
			break
		}
	}
	if !hasDiagnostics {
		return params
	}

	sanitized := make(map[string]any, len(params))
	for key, value := range params {
		if strings.HasPrefix(key, "_") {
			continue
		}
		sanitized[key] = value
	}
	return sanitized
}

func summarizePhaseGroupStatement(cypher string) string {
	trimmed := strings.TrimSpace(cypher)
	if trimmed == "" {
		return ""
	}
	lines := strings.Split(trimmed, "\n")
	if len(lines) > 2 {
		lines = lines[:2]
	}
	trimmed = strings.Join(lines, " | ")
	if len(trimmed) > 120 {
		return trimmed[:120]
	}
	return trimmed
}

func ingesterContentBeforeCanonical(getenv func(string) string) bool {
	return strings.TrimSpace(getenv("PCG_QUERY_PROFILE")) == "local_authoritative"
}

func nornicDBCanonicalWriteTimeout(getenv func(string) string) time.Duration {
	raw := strings.TrimSpace(getenv(canonicalWriteTimeoutEnv))
	if raw == "" {
		return defaultNornicDBCanonicalWriteTimeout
	}
	parsed, err := time.ParseDuration(raw)
	if err != nil || parsed <= 0 {
		return defaultNornicDBCanonicalWriteTimeout
	}
	return parsed
}

func nornicDBCanonicalGroupedWrites(getenv func(string) string) (bool, error) {
	raw := strings.TrimSpace(getenv(nornicDBCanonicalGroupedWritesEnv))
	if raw == "" {
		return false, nil
	}
	enabled, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("parse %s=%q: %w", nornicDBCanonicalGroupedWritesEnv, raw, err)
	}
	return enabled, nil
}

func nornicDBPhaseGroupStatements(getenv func(string) string) (int, error) {
	raw := strings.TrimSpace(getenv(nornicDBPhaseGroupStatementsEnv))
	if raw == "" {
		return defaultNornicDBPhaseGroupStatements, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("parse %s=%q: must be a positive integer", nornicDBPhaseGroupStatementsEnv, raw)
	}
	return n, nil
}

func nornicDBEntityPhaseGroupStatements(getenv func(string) string) (int, error) {
	raw := strings.TrimSpace(getenv(nornicDBEntityPhaseStatementsEnv))
	if raw == "" {
		return defaultNornicDBEntityPhaseStatements, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("parse %s=%q: must be a positive integer", nornicDBEntityPhaseStatementsEnv, raw)
	}
	return n, nil
}

func nornicDBEntityBatchSize(getenv func(string) string) (int, error) {
	raw := strings.TrimSpace(getenv(nornicDBEntityBatchSizeEnv))
	if raw == "" {
		return defaultNornicDBEntityBatchSize, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("parse %s=%q: must be a positive integer", nornicDBEntityBatchSizeEnv, raw)
	}
	return n, nil
}

func neo4jBatchSize(getenv func(string) string) int {
	raw := strings.TrimSpace(getenv("PCG_NEO4J_BATCH_SIZE"))
	if raw == "" {
		return 0
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0
	}
	return n
}

type ingesterNeo4jExecutor struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
	TxTimeout    time.Duration
}

func (e ingesterNeo4jExecutor) Execute(ctx context.Context, statement sourceneo4j.Statement) error {
	if e.Driver == nil {
		return fmt.Errorf("neo4j driver is required")
	}

	session := e.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: e.DatabaseName,
	})
	defer func() {
		_ = session.Close(ctx)
	}()

	result, err := session.Run(ctx, statement.Cypher, statement.Parameters, e.transactionConfigurers()...)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
}

func (e ingesterNeo4jExecutor) ExecuteGroup(ctx context.Context, stmts []sourceneo4j.Statement) error {
	if e.Driver == nil {
		return fmt.Errorf("neo4j driver is required")
	}
	if len(stmts) == 0 {
		return nil
	}

	session := e.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: e.DatabaseName,
	})
	defer func() {
		_ = session.Close(ctx)
	}()

	_, err := session.ExecuteWrite(ctx, func(tx neo4jdriver.ManagedTransaction) (any, error) {
		for _, stmt := range stmts {
			result, runErr := tx.Run(ctx, stmt.Cypher, stmt.Parameters)
			if runErr != nil {
				return nil, runErr
			}
			if _, consumeErr := result.Consume(ctx); consumeErr != nil {
				return nil, consumeErr
			}
		}
		return nil, nil
	}, e.transactionConfigurers()...)
	return err
}

func (e ingesterNeo4jExecutor) transactionConfigurers() []func(*neo4jdriver.TransactionConfig) {
	if e.TxTimeout <= 0 {
		return nil
	}
	return []func(*neo4jdriver.TransactionConfig){neo4jdriver.WithTxTimeout(e.TxTimeout)}
}

func canonicalTransactionTimeout(graphBackend runtimecfg.GraphBackend, getenv func(string) string) time.Duration {
	if graphBackend != runtimecfg.GraphBackendNornicDB {
		return 0
	}
	return nornicDBCanonicalWriteTimeout(getenv)
}

type ingesterNeo4jDriverCloser struct {
	Driver neo4jdriver.DriverWithContext
}

func (c ingesterNeo4jDriverCloser) Close() error {
	return closeIngesterNeo4jDriver(c.Driver)
}

func closeIngesterNeo4jDriver(driver neo4jdriver.DriverWithContext) error {
	if driver == nil {
		return nil
	}

	closeCtx, cancel := context.WithTimeout(context.Background(), ingesterConnectionTimeout)
	defer cancel()
	return driver.Close(closeCtx)
}
