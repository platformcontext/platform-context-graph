package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"runtime"
	"slices"
	"sort"
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
	// Entity statements carry the heaviest canonical payloads on the current
	// self-repo dogfood lane, so NornicDB needs a lower grouped-transaction cap
	// here than on lighter canonical phases.
	defaultNornicDBEntityPhaseStatements = 25
	// File upserts are lighter than entity rows but huge repos can emit many
	// 500-row file statements. Keep this phase narrow without lowering the
	// global non-entity phase-group cap.
	defaultNornicDBFilePhaseStatements = 5
	// Long-running labels such as Variable need cumulative visibility before
	// the whole entities phase completes, otherwise tuning waits on hour-scale
	// dogfood runs.
	defaultNornicDBEntityLabelSummaryExecutions = 10
	// Normal NornicDB entity upserts stay bounded to 100 rows so we do not send
	// 500-row canonical entity statements through the slower Bolt path.
	defaultNornicDBEntityBatchSize = 100
	// Function entities remain the heaviest row shape inside the broader entity
	// phase, so they get a narrower row cap than other entity labels.
	// Function rows are the highest-cost entity family on the self-repo dogfood
	// lane. The first narrowed 10-row default lowered per-statement cost, but it
	// fragmented the lane too much; 15 rows keeps Function chunks bounded while
	// still reaching Variable at the healthier ~20s band.
	defaultNornicDBFunctionEntityBatchSize = 15
	// Struct entities were the next heavy family on the self-repo dogfood lane
	// once Function rows were narrowed, so they get the next smaller row cap.
	defaultNornicDBStructEntityBatchSize = 50
	// Variable remains the next repo-scale hot family after Function. Fresh
	// self-repo reruns still spent roughly 22s-31s per five-statement chunk at
	// 25 rows, so the built-in default now narrows Variable rows further while
	// keeping the grouped-statement cap unchanged for a clean next comparison.
	defaultNornicDBVariableEntityBatchSize = 10
	// K8sResource rows can cluster heavily in one Helm/Kustomize YAML file.
	// File-scoped inline containment preserves NornicDB row binding correctness,
	// so the row cap must be narrow as well as the grouped statement cap.
	defaultNornicDBK8sResourceEntityBatchSize = 5
	// Function entity statements remain the slowest grouped transaction shape
	// on the self-repo dogfood lane. Ten-statement groups still drifted into
	// the high-30s seconds, so NornicDB now keeps that family on the same
	// conservative grouped cap as Variable for the built-in default lane.
	defaultNornicDBFunctionEntityPhaseStatements = 5
	// Struct entity statements were the next slowest family after Function, but
	// still lighter than Function rows, so they keep a slightly looser cap.
	defaultNornicDBStructEntityPhaseStatements = 15
	// Variable entities hit the first post-Function repo-scale timeout at the
	// broader entity phase limit, so they need the same conservative grouped
	// statement cap as Function for the current dogfood lane.
	defaultNornicDBVariableEntityPhaseStatements = 5
	// K8sResource rows are small individually, but one manifest can contain many
	// resources. Keep their grouped transaction cap narrow so large
	// Helm/Kustomize repos do not timeout inside one Bolt transaction.
	defaultNornicDBK8sResourceEntityPhaseStatements = 5
	canonicalWriteTimeoutEnv                        = "PCG_CANONICAL_WRITE_TIMEOUT"
	nornicDBCanonicalGroupedWritesEnv               = "PCG_NORNICDB_CANONICAL_GROUPED_WRITES"
	nornicDBPhaseGroupStatementsEnv                 = "PCG_NORNICDB_PHASE_GROUP_STATEMENTS"
	nornicDBFilePhaseGroupStatementsEnv             = "PCG_NORNICDB_FILE_PHASE_GROUP_STATEMENTS"
	nornicDBEntityPhaseStatementsEnv                = "PCG_NORNICDB_ENTITY_PHASE_GROUP_STATEMENTS"
	nornicDBEntityBatchSizeEnv                      = "PCG_NORNICDB_ENTITY_BATCH_SIZE"
	nornicDBEntityLabelBatchSizesEnv                = "PCG_NORNICDB_ENTITY_LABEL_BATCH_SIZES"
	nornicDBEntityLabelPhaseGroupStatementsEnv      = "PCG_NORNICDB_ENTITY_LABEL_PHASE_GROUP_STATEMENTS"
	nornicDBBatchedEntityContainmentEnv             = "PCG_NORNICDB_BATCHED_ENTITY_CONTAINMENT"
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
	filePhaseStatements := defaultNornicDBFilePhaseStatements
	entityPhaseStatements := defaultNornicDBEntityPhaseStatements
	entityBatchSize := 0
	entityLabelPhaseStatements := map[string]int(nil)
	nornicDBBatchedEntityContainment := false
	if graphBackend == runtimecfg.GraphBackendNornicDB {
		nornicDBGroupedWrites, err = nornicDBCanonicalGroupedWrites(getenv)
		if err != nil {
			return nil, nil, err
		}
		phaseGroupStatements, err = nornicDBPhaseGroupStatements(getenv)
		if err != nil {
			return nil, nil, err
		}
		filePhaseStatements, err = nornicDBFilePhaseGroupStatements(getenv)
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
		entityLabelPhaseStatements, err = nornicDBEntityLabelPhaseGroupStatements(getenv, entityPhaseStatements)
		if err != nil {
			return nil, nil, err
		}
		nornicDBBatchedEntityContainment, err = nornicDBBatchedEntityContainmentEnabled(getenv)
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
			filePhaseStatements,
			entityPhaseStatements,
			entityLabelPhaseStatements,
			tracer,
			instruments,
		),
		neo4jBatchSize(getenv),
		instruments,
	)
	if entityBatchSize > 0 {
		writer = writer.WithEntityBatchSize(entityBatchSize)
	}
	if graphBackend == runtimecfg.GraphBackendNornicDB {
		if nornicDBBatchedEntityContainment {
			writer = writer.WithBatchedEntityContainmentInEntityUpsert()
			slog.Warn("NornicDB batched entity containment enabled for patched-binary evaluation",
				"graph_backend", string(graphBackend),
				"env_var", nornicDBBatchedEntityContainmentEnv)
		} else {
			writer = writer.WithEntityContainmentInEntityUpsert()
		}
		labelBatchSizes, err := nornicDBEntityLabelBatchSizes(getenv, entityBatchSize)
		if err != nil {
			return nil, nil, err
		}
		for _, label := range orderedEntityBatchLabels(labelBatchSizes) {
			batchSize := labelBatchSizes[label]
			writer = writer.WithEntityLabelBatchSize(label, batchSize)
		}
	}

	return writer, ingesterNeo4jDriverCloser{Driver: driver}, nil
}

func capOptionalBatchSize(configured int, limit int) int {
	if configured <= 0 {
		return limit
	}
	if limit <= 0 || configured <= limit {
		return configured
	}
	return limit
}

func orderedEntityBatchLabels(labelBatchSizes map[string]int) []string {
	labels := make([]string, 0, len(labelBatchSizes))
	for label := range labelBatchSizes {
		labels = append(labels, label)
	}
	slices.Sort(labels)
	return labels
}

func defaultNornicDBEntityLabelBatchSizes(entityBatchSize int) map[string]int {
	return map[string]int{
		"Function": capOptionalBatchSize(entityBatchSize, defaultNornicDBFunctionEntityBatchSize),
		// Struct payloads have been slower than the broad entity default, but
		// still materially lighter than Function rows on the self-repo dogfood
		// lane, so they keep a looser cap than Function.
		"Struct": capOptionalBatchSize(entityBatchSize, defaultNornicDBStructEntityBatchSize),
		// Variable rows timed out at repo scale with the broader default, so
		// they follow the same narrowed row cap as Struct for now.
		"Variable": capOptionalBatchSize(entityBatchSize, defaultNornicDBVariableEntityBatchSize),
		// K8sResource rows need a per-statement row cap because file-scoped
		// inline containment can otherwise put dozens of resources from one YAML
		// file into a single NornicDB statement.
		"K8sResource": capOptionalBatchSize(entityBatchSize, defaultNornicDBK8sResourceEntityBatchSize),
	}
}

func defaultNornicDBEntityLabelPhaseGroupStatements(entityPhaseStatements int) map[string]int {
	return map[string]int{
		"Function":    capOptionalBatchSize(entityPhaseStatements, defaultNornicDBFunctionEntityPhaseStatements),
		"K8sResource": capOptionalBatchSize(entityPhaseStatements, defaultNornicDBK8sResourceEntityPhaseStatements),
		"Struct":      capOptionalBatchSize(entityPhaseStatements, defaultNornicDBStructEntityPhaseStatements),
		"Variable":    capOptionalBatchSize(entityPhaseStatements, defaultNornicDBVariableEntityPhaseStatements),
	}
}

func nornicDBEntityLabelBatchSizes(getenv func(string) string, entityBatchSize int) (map[string]int, error) {
	labelBatchSizes := defaultNornicDBEntityLabelBatchSizes(entityBatchSize)
	raw := strings.TrimSpace(getenv(nornicDBEntityLabelBatchSizesEnv))
	if raw == "" {
		return labelBatchSizes, nil
	}

	for _, entry := range strings.Split(raw, ",") {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}
		label, value, ok := strings.Cut(entry, "=")
		if !ok {
			return nil, fmt.Errorf("parse %s=%q: entries must be Label=size", nornicDBEntityLabelBatchSizesEnv, raw)
		}
		label = strings.TrimSpace(label)
		value = strings.TrimSpace(value)
		if label == "" {
			return nil, fmt.Errorf("parse %s=%q: label must be non-empty", nornicDBEntityLabelBatchSizesEnv, raw)
		}
		batchSize, err := strconv.Atoi(value)
		if err != nil || batchSize <= 0 {
			return nil, fmt.Errorf("parse %s=%q: label %q must have a positive integer size", nornicDBEntityLabelBatchSizesEnv, raw, label)
		}
		labelBatchSizes[label] = capOptionalBatchSize(entityBatchSize, batchSize)
	}
	return labelBatchSizes, nil
}

func nornicDBEntityLabelPhaseGroupStatements(getenv func(string) string, entityPhaseStatements int) (map[string]int, error) {
	labelStatementLimits := defaultNornicDBEntityLabelPhaseGroupStatements(entityPhaseStatements)
	raw := strings.TrimSpace(getenv(nornicDBEntityLabelPhaseGroupStatementsEnv))
	if raw == "" {
		return labelStatementLimits, nil
	}

	for _, entry := range strings.Split(raw, ",") {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}
		label, value, ok := strings.Cut(entry, "=")
		if !ok {
			return nil, fmt.Errorf("parse %s=%q: entries must be Label=size", nornicDBEntityLabelPhaseGroupStatementsEnv, raw)
		}
		label = strings.TrimSpace(label)
		value = strings.TrimSpace(value)
		if label == "" {
			return nil, fmt.Errorf("parse %s=%q: label must be non-empty", nornicDBEntityLabelPhaseGroupStatementsEnv, raw)
		}
		statementCount, err := strconv.Atoi(value)
		if err != nil || statementCount <= 0 {
			return nil, fmt.Errorf("parse %s=%q: label %q must have a positive integer size", nornicDBEntityLabelPhaseGroupStatementsEnv, raw, label)
		}
		labelStatementLimits[label] = capOptionalBatchSize(entityPhaseStatements, statementCount)
	}
	return labelStatementLimits, nil
}

func canonicalExecutorForGraphBackend(
	rawExecutor sourceneo4j.Executor,
	graphBackend runtimecfg.GraphBackend,
	nornicDBTimeout time.Duration,
	nornicDBGroupedWrites bool,
	nornicDBPhaseGroupStatements int,
	nornicDBFilePhaseStatements int,
	nornicDBEntityPhaseStatements int,
	nornicDBEntityLabelPhaseStatements map[string]int,
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
			inner:                    bounded,
			maxStatements:            nornicDBPhaseGroupStatements,
			fileMaxStatements:        nornicDBFilePhaseStatements,
			entityMaxStatements:      nornicDBEntityPhaseStatements,
			entityLabelMaxStatements: nornicDBEntityLabelPhaseStatements,
		}
	}
	return instrumented
}

type nornicDBPhaseGroupExecutor struct {
	inner                    sourceneo4j.Executor
	maxStatements            int
	fileMaxStatements        int
	entityMaxStatements      int
	entityLabelMaxStatements map[string]int
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
		if allStatementsUseOperation(stmts, sourceneo4j.OperationCanonicalRetract) {
			return e.executeSequentialRetractPhase(ctx, stmts)
		}
		if statementPhaseUsesEntityLabelStats(statementPhase(stmts)) {
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

func (e nornicDBPhaseGroupExecutor) executeSequentialRetractPhase(
	ctx context.Context,
	stmts []sourceneo4j.Statement,
) error {
	for i, stmt := range stmts {
		statementStart := time.Now()
		statementSummary := summarizePhaseGroupChunk([]sourceneo4j.Statement{stmt})
		if err := e.inner.Execute(ctx, sanitizedStatement(stmt)); err != nil {
			return fmt.Errorf(
				"phase-group retract statement %d/%d (duration=%s, first_statement=%q): %w",
				i+1,
				len(stmts),
				time.Since(statementStart),
				statementSummary,
				err,
			)
		}
	}
	return nil
}

func (e nornicDBPhaseGroupExecutor) executeEntityPhaseGroup(
	ctx context.Context,
	ge sourceneo4j.GroupExecutor,
	stmts []sourceneo4j.Statement,
) error {
	labelStats := make(map[string]*entityPhaseLabelStats)
	phase := statementPhase(stmts)
	grouped := make([]sourceneo4j.Statement, 0, len(stmts))
	groupedLabel := ""
	flushGrouped := func() error {
		if len(grouped) == 0 {
			return nil
		}
		err := e.executeGroupedChunksObserved(
			ctx,
			ge,
			grouped,
			e.phaseGroupStatementLimit(grouped),
			func(chunk []sourceneo4j.Statement, chunkDuration time.Duration) {
				label := entityStatementLabel(chunk[0])
				stats := ensureEntityPhaseLabelStats(labelStats, phase, label)
				stats.recordChunk(chunk, chunkDuration)
				logEntityPhaseLabelSummaryIfDue(stats, false)
			},
		)
		grouped = grouped[:0]
		groupedLabel = ""
		return err
	}

	for i, stmt := range stmts {
		if statementPhaseGroupMode(stmt) == sourceneo4j.PhaseGroupModeExecuteOnly {
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
					phase,
					time.Since(statementStart),
					statementSummary,
					err,
				)
			}
			slog.Info(
				"nornicdb phase-group singleton completed",
				"statement_index", i+1,
				"statement_count", len(stmts),
				"phase", phase,
				"duration_s", time.Since(statementStart).Seconds(),
				"first_statement", statementSummary,
			)
			stats := ensureEntityPhaseLabelStats(labelStats, phase, entityStatementLabel(stmt))
			stats.recordSingleton(stmt, time.Since(statementStart))
			logEntityPhaseLabelSummaryIfDue(stats, false)
			continue
		}
		stmtLabel := entityStatementLabel(stmt)
		if len(grouped) > 0 && stmtLabel != groupedLabel {
			completedLabel := groupedLabel
			if err := flushGrouped(); err != nil {
				return err
			}
			logEntityPhaseLabelSummaryIfDue(labelStats[completedLabel], true)
		}
		grouped = append(grouped, stmt)
		if groupedLabel == "" {
			groupedLabel = stmtLabel
		}
		if len(grouped) >= e.phaseGroupStatementLimit(grouped) {
			if err := flushGrouped(); err != nil {
				return err
			}
		}
	}

	if err := flushGrouped(); err != nil {
		return err
	}
	logEntityPhaseLabelSummaries(labelStats, true)
	return nil
}

func (e nornicDBPhaseGroupExecutor) executeGroupedChunks(
	ctx context.Context,
	ge sourceneo4j.GroupExecutor,
	stmts []sourceneo4j.Statement,
	maxStatements int,
) error {
	return e.executeGroupedChunksObserved(ctx, ge, stmts, maxStatements, nil)
}

func (e nornicDBPhaseGroupExecutor) executeGroupedChunksObserved(
	ctx context.Context,
	ge sourceneo4j.GroupExecutor,
	stmts []sourceneo4j.Statement,
	maxStatements int,
	observer func([]sourceneo4j.Statement, time.Duration),
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
		if observer != nil {
			observer(chunk, chunkDuration)
		}
		slog.Info(
			"nornicdb phase-group chunk completed",
			"chunk_index", chunkIndex,
			"chunk_count", totalChunks,
			"statement_start", start+1,
			"statement_end", end,
			"statement_count", end-start,
			"duration_s", chunkDuration.Seconds(),
			"first_statement", statementSummary,
		)
	}
	return nil
}

type entityPhaseLabelStats struct {
	phase               string
	label               string
	rows                int
	statements          int
	executions          int
	groupedChunks       int
	singletonStatements int
	totalDuration       time.Duration
	maxDuration         time.Duration
	maxStatementRows    int
	maxExecutionRows    int
	loggedExecutions    int
	completeLogged      bool
}

func ensureEntityPhaseLabelStats(stats map[string]*entityPhaseLabelStats, phase string, label string) *entityPhaseLabelStats {
	phase = strings.TrimSpace(phase)
	if phase == "" {
		phase = "unknown"
	}
	label = strings.TrimSpace(label)
	if label == "" {
		label = "unknown"
	}
	if existing := stats[label]; existing != nil {
		return existing
	}
	created := &entityPhaseLabelStats{phase: phase, label: label}
	stats[label] = created
	return created
}

func (s *entityPhaseLabelStats) recordChunk(chunk []sourceneo4j.Statement, duration time.Duration) {
	if s == nil || len(chunk) == 0 {
		return
	}
	s.executions++
	s.groupedChunks++
	s.totalDuration += duration
	if duration > s.maxDuration {
		s.maxDuration = duration
	}
	executionRows := 0
	for _, stmt := range chunk {
		rows := entityStatementRowCount(stmt)
		s.rows += rows
		s.statements++
		executionRows += rows
		if rows > s.maxStatementRows {
			s.maxStatementRows = rows
		}
	}
	if executionRows > s.maxExecutionRows {
		s.maxExecutionRows = executionRows
	}
}

func (s *entityPhaseLabelStats) recordSingleton(stmt sourceneo4j.Statement, duration time.Duration) {
	if s == nil {
		return
	}
	rows := entityStatementRowCount(stmt)
	s.rows += rows
	s.statements++
	s.executions++
	s.singletonStatements++
	s.totalDuration += duration
	if duration > s.maxDuration {
		s.maxDuration = duration
	}
	if rows > s.maxStatementRows {
		s.maxStatementRows = rows
	}
	if rows > s.maxExecutionRows {
		s.maxExecutionRows = rows
	}
}

func logEntityPhaseLabelSummaryIfDue(summary *entityPhaseLabelStats, complete bool) {
	if summary == nil {
		return
	}
	if !complete && summary.executions-summary.loggedExecutions < defaultNornicDBEntityLabelSummaryExecutions {
		return
	}
	logEntityPhaseLabelSummary(summary, complete)
}

func logEntityPhaseLabelSummaries(stats map[string]*entityPhaseLabelStats, complete bool) {
	if len(stats) == 0 {
		return
	}
	labels := make([]string, 0, len(stats))
	for label := range stats {
		labels = append(labels, label)
	}
	sort.Strings(labels)
	for _, label := range labels {
		summary := stats[label]
		if summary == nil {
			continue
		}
		logEntityPhaseLabelSummary(summary, complete)
	}
}

func logEntityPhaseLabelSummary(summary *entityPhaseLabelStats, complete bool) {
	if summary == nil {
		return
	}
	if complete && summary.completeLogged {
		return
	}
	avgRowsPerStatement := 0.0
	if summary.statements > 0 {
		avgRowsPerStatement = float64(summary.rows) / float64(summary.statements)
	}
	avgExecutionDuration := 0.0
	if summary.executions > 0 {
		avgExecutionDuration = summary.totalDuration.Seconds() / float64(summary.executions)
	}
	slog.Info(
		"nornicdb entity label summary",
		"phase", summary.phase,
		"label", summary.label,
		"complete", complete,
		"rows", summary.rows,
		"statements", summary.statements,
		"executions", summary.executions,
		"grouped_chunks", summary.groupedChunks,
		"singleton_statements", summary.singletonStatements,
		"total_duration_s", summary.totalDuration.Seconds(),
		"avg_execution_duration_s", avgExecutionDuration,
		"max_execution_duration_s", summary.maxDuration.Seconds(),
		"avg_rows_per_statement", avgRowsPerStatement,
		"max_statement_rows", summary.maxStatementRows,
		"max_execution_rows", summary.maxExecutionRows,
	)
	summary.loggedExecutions = summary.executions
	if complete {
		summary.completeLogged = true
	}
}

func entityStatementRowCount(stmt sourceneo4j.Statement) int {
	if rows, ok := stmt.Parameters["rows"].([]map[string]any); ok {
		return len(rows)
	}
	if rows, ok := stmt.Parameters["rows"].([]any); ok {
		return len(rows)
	}
	if _, ok := stmt.Parameters["entity_id"]; ok {
		return 1
	}
	return 0
}

func (e nornicDBPhaseGroupExecutor) phaseGroupStatementLimit(stmts []sourceneo4j.Statement) int {
	phase := statementPhase(stmts)
	if phase == sourceneo4j.CanonicalPhaseFiles {
		if e.fileMaxStatements > 0 {
			return e.fileMaxStatements
		}
		return defaultNornicDBFilePhaseStatements
	}
	if statementPhaseUsesEntityLabelStats(phase) {
		if label := entityStatementLabel(stmts[0]); label != "" && e.entityLabelMaxStatements != nil {
			if limit := e.entityLabelMaxStatements[label]; limit > 0 {
				return limit
			}
		}
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

func statementPhaseUsesEntityLabelStats(phase string) bool {
	switch strings.TrimSpace(phase) {
	case sourceneo4j.CanonicalPhaseEntities, sourceneo4j.CanonicalPhaseEntityContainment:
		return true
	default:
		return false
	}
}

func statementPhase(stmts []sourceneo4j.Statement) string {
	if len(stmts) == 0 {
		return ""
	}
	phase, _ := stmts[0].Parameters[sourceneo4j.StatementMetadataPhaseKey].(string)
	return strings.TrimSpace(phase)
}

func statementPhaseGroupMode(stmt sourceneo4j.Statement) string {
	mode, _ := stmt.Parameters[sourceneo4j.StatementMetadataPhaseGroupModeKey].(string)
	return strings.TrimSpace(mode)
}

func entityStatementLabel(stmt sourceneo4j.Statement) string {
	label, _ := stmt.Parameters[sourceneo4j.StatementMetadataEntityLabelKey].(string)
	return strings.TrimSpace(label)
}

func allStatementsUseOperation(stmts []sourceneo4j.Statement, operation sourceneo4j.Operation) bool {
	if len(stmts) == 0 {
		return false
	}
	for _, stmt := range stmts {
		if stmt.Operation != operation {
			return false
		}
	}
	return true
}

func summarizePhaseGroupChunk(stmts []sourceneo4j.Statement) string {
	if len(stmts) == 0 {
		return ""
	}
	if summary, ok := stmts[0].Parameters[sourceneo4j.StatementMetadataSummaryKey].(string); ok && strings.TrimSpace(summary) != "" {
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

func nornicDBBatchedEntityContainmentEnabled(getenv func(string) string) (bool, error) {
	raw := strings.TrimSpace(getenv(nornicDBBatchedEntityContainmentEnv))
	if raw == "" {
		return false, nil
	}
	enabled, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("parse %s=%q: %w", nornicDBBatchedEntityContainmentEnv, raw, err)
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

func nornicDBFilePhaseGroupStatements(getenv func(string) string) (int, error) {
	raw := strings.TrimSpace(getenv(nornicDBFilePhaseGroupStatementsEnv))
	if raw == "" {
		return defaultNornicDBFilePhaseStatements, nil
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("parse %s=%q: must be a positive integer", nornicDBFilePhaseGroupStatementsEnv, raw)
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
