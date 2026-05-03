package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"strconv"
	"strings"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourcecypher "github.com/platformcontext/platform-context-graph/go/internal/storage/cypher"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const bootstrapIndexConnectionTimeout = 10 * time.Second

func buildBootstrapCollector(
	ctx context.Context,
	database bootstrapDB,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (collectorDeps, error) {
	instrumentedDB := &postgres.InstrumentedDB{
		Inner:       database,
		Tracer:      tracer,
		Instruments: instruments,
		StoreName:   "bootstrap-index",
	}

	config, err := collector.LoadRepoSyncConfig("bootstrap-index", getenv)
	if err != nil {
		return collectorDeps{}, err
	}
	discoveryOptions, err := collector.LoadDiscoveryOptionsFromEnv(getenv)
	if err != nil {
		return collectorDeps{}, err
	}

	source := &collector.GitSource{
		Component: "bootstrap-index",
		Selector:  collector.NativeRepositorySelector{Config: config},
		Snapshotter: collector.NativeRepositorySnapshotter{
			ParseWorkers:     config.ParseWorkers,
			DiscoveryOptions: discoveryOptions,
			Tracer:           tracer,
			Instruments:      instruments,
			Logger:           logger,
		},
		SnapshotWorkers:        config.SnapshotWorkers,
		LargeRepoThreshold:     config.LargeRepoThreshold,
		LargeRepoMaxConcurrent: config.LargeRepoMaxConcurrent,
		StreamBuffer:           config.StreamBuffer,
		Tracer:                 tracer,
		Instruments:            instruments,
		Logger:                 logger,
	}

	committer := postgres.NewIngestionStore(instrumentedDB)
	committer.SkipRelationshipBackfill = true
	committer.Logger = logger

	return collectorDeps{
		source:    source,
		committer: committer,
	}, nil
}

func buildBootstrapProjector(
	ctx context.Context,
	database bootstrapDB,
	canonicalWriter projector.CanonicalWriter,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (projectorDeps, error) {
	instrumentedDB := &postgres.InstrumentedDB{
		Inner:       database,
		Tracer:      tracer,
		Instruments: instruments,
		StoreName:   "bootstrap-index",
	}

	projectorQueue := postgres.NewProjectorQueue(instrumentedDB, "bootstrap-index", time.Minute)
	reducerQueue := postgres.NewReducerQueue(instrumentedDB, "bootstrap-index", time.Minute)
	contentConfig, err := content.LoadWriterConfig(getenv)
	if err != nil {
		return projectorDeps{}, err
	}
	runtime := projector.Runtime{
		CanonicalWriter: canonicalWriter,
		ContentWriter: postgres.NewContentWriter(instrumentedDB).
			WithLogger(logger).
			WithEntityBatchSize(contentConfig.EntityBatchSize),
		IntentWriter:   reducerQueue,
		PhasePublisher: postgres.NewGraphProjectionPhaseStateStore(instrumentedDB),
		RepairQueue:    postgres.NewGraphProjectionPhaseRepairQueueStore(instrumentedDB),
		Tracer:         tracer,
		Instruments:    instruments,
		Logger:         logger,
	}

	return projectorDeps{
		workSource:        projectorQueue,
		factStore:         postgres.NewFactStore(instrumentedDB),
		runner:            runtime,
		workSink:          projectorQueue,
		heartbeater:       projectorQueue,
		heartbeatInterval: bootstrapProjectorHeartbeatInterval(projectorQueue.LeaseDuration),
	}, nil
}

// bootstrapProjectorHeartbeatInterval renews leases well before expiry while
// avoiding excessive wakeups for long lease durations.
func bootstrapProjectorHeartbeatInterval(leaseDuration time.Duration) time.Duration {
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

// neo4jBatchSize reads PCG_NEO4J_BATCH_SIZE from the environment.
// Returns 0 (use default) if unset or invalid.
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

func openBootstrapCanonicalWriter(
	parent context.Context,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) (projector.CanonicalWriter, io.Closer, error) {
	graphBackend, err := runtimecfg.LoadGraphBackend(getenv)
	if err != nil {
		return nil, nil, err
	}
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, err
	}

	rawExecutor := bootstrapNeo4jExecutor{
		Driver:       driver,
		DatabaseName: cfg.DatabaseName,
		TxTimeout:    bootstrapCanonicalTransactionTimeout(graphBackend, getenv),
	}

	executor, err := bootstrapCanonicalExecutorForGraphBackend(
		rawExecutor,
		graphBackend,
		getenv,
		tracer,
		instruments,
	)
	if err != nil {
		_ = closeBootstrapNeo4jDriver(driver)
		return nil, nil, err
	}

	writer := sourcecypher.NewCanonicalNodeWriter(
		executor,
		neo4jBatchSize(getenv),
		instruments,
	)
	if graphBackend == runtimecfg.GraphBackendNornicDB {
		fileBatchSize, err := nornicDBPositiveIntEnv(getenv, nornicDBFileBatchSizeEnv, defaultNornicDBFileBatchSize)
		if err != nil {
			_ = closeBootstrapNeo4jDriver(driver)
			return nil, nil, err
		}
		entityBatchSize, err := nornicDBPositiveIntEnv(getenv, nornicDBEntityBatchSizeEnv, defaultNornicDBEntityBatchSize)
		if err != nil {
			_ = closeBootstrapNeo4jDriver(driver)
			return nil, nil, err
		}
		labelBatchSizes, err := nornicDBEntityLabelBatchSizes(getenv, entityBatchSize)
		if err != nil {
			_ = closeBootstrapNeo4jDriver(driver)
			return nil, nil, err
		}
		writer = writer.
			WithFileBatchSize(fileBatchSize).
			WithEntityBatchSize(entityBatchSize).
			WithEntityContainmentInEntityUpsert()
		for label, batchSize := range labelBatchSizes {
			writer = writer.WithEntityLabelBatchSize(label, batchSize)
		}
	}

	return writer, bootstrapNeo4jDriverCloser{Driver: driver}, nil
}

type bootstrapNeo4jExecutor struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
	TxTimeout    time.Duration
}

func (e bootstrapNeo4jExecutor) ExecuteGroup(ctx context.Context, stmts []sourcecypher.Statement) error {
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

func (e bootstrapNeo4jExecutor) Execute(ctx context.Context, statement sourcecypher.Statement) error {
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

func (e bootstrapNeo4jExecutor) transactionConfigurers() []func(*neo4jdriver.TransactionConfig) {
	if e.TxTimeout <= 0 {
		return nil
	}
	return []func(*neo4jdriver.TransactionConfig){neo4jdriver.WithTxTimeout(e.TxTimeout)}
}

func bootstrapCanonicalTransactionTimeout(graphBackend runtimecfg.GraphBackend, getenv func(string) string) time.Duration {
	if graphBackend != runtimecfg.GraphBackendNornicDB {
		return 0
	}
	return nornicDBCanonicalWriteTimeout(getenv)
}

type bootstrapNeo4jDriverCloser struct {
	Driver neo4jdriver.DriverWithContext
}

func (c bootstrapNeo4jDriverCloser) Close() error {
	return closeBootstrapNeo4jDriver(c.Driver)
}

func closeBootstrapNeo4jDriver(driver neo4jdriver.DriverWithContext) error {
	if driver == nil {
		return nil
	}

	closeCtx, cancel := context.WithTimeout(context.Background(), bootstrapIndexConnectionTimeout)
	defer cancel()
	return driver.Close(closeCtx)
}
