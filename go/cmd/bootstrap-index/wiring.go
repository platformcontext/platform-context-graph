package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
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

	source := &collector.GitSource{
		Component:   "bootstrap-index",
		Selector:    collector.NativeRepositorySelector{Config: config},
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
	}

	return collectorDeps{
		source:    source,
		committer: postgres.NewIngestionStore(instrumentedDB),
	}, nil
}

func buildBootstrapProjector(
	ctx context.Context,
	database bootstrapDB,
	graphWriter graph.Writer,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) (projectorDeps, error) {
	instrumentedDB := &postgres.InstrumentedDB{
		Inner:       database,
		Tracer:      tracer,
		Instruments: instruments,
		StoreName:   "bootstrap-index",
	}

	projectorQueue := postgres.NewProjectorQueue(instrumentedDB, "bootstrap-index", time.Minute)
	reducerQueue := postgres.NewReducerQueue(instrumentedDB, "bootstrap-index", time.Minute)
	runtime := projector.Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: postgres.NewContentWriter(instrumentedDB),
		IntentWriter:  reducerQueue,
		Tracer:        tracer,
		Instruments:   instruments,
	}

	return projectorDeps{
		workSource: projectorQueue,
		factStore:  postgres.NewFactStore(instrumentedDB),
		runner:     runtime,
		workSink:   projectorQueue,
	}, nil
}

func openBootstrapGraphWriter(
	parent context.Context,
	getenv func(string) string,
) (graph.Writer, io.Closer, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, err
	}

	return sourceneo4j.Adapter{
			Executor: bootstrapNeo4jExecutor{
				Driver:       driver,
				DatabaseName: cfg.DatabaseName,
			},
		},
		bootstrapNeo4jDriverCloser{Driver: driver},
		nil
}

type bootstrapNeo4jExecutor struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
}

func (e bootstrapNeo4jExecutor) Execute(ctx context.Context, statement sourceneo4j.Statement) error {
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

	result, err := session.Run(ctx, statement.Cypher, statement.Parameters)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
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
