package main

import (
	"context"
	"fmt"
	"io"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const bootstrapIndexConnectionTimeout = 10 * time.Second

func buildBootstrapCollector(
	ctx context.Context,
	database bootstrapDB,
	getenv func(string) string,
) (collectorDeps, error) {
	sqlDB, ok := database.(postgres.ExecQueryer)
	if !ok {
		return collectorDeps{}, fmt.Errorf("bootstrap collector requires a SQL database")
	}

	config, err := collector.LoadRepoSyncConfig("bootstrap-index", getenv)
	if err != nil {
		return collectorDeps{}, err
	}

	source := &collector.GitSource{
		Component:   "bootstrap-index",
		Selector:    collector.NativeRepositorySelector{Config: config},
		Snapshotter: collector.NativeRepositorySnapshotter{},
	}

	return collectorDeps{
		source:    source,
		committer: postgres.NewIngestionStore(sqlDB),
	}, nil
}

func buildBootstrapProjector(
	ctx context.Context,
	database bootstrapDB,
	graphWriter graph.Writer,
	getenv func(string) string,
) (projectorDeps, error) {
	sqlDB, ok := database.(postgres.ExecQueryer)
	if !ok {
		return projectorDeps{}, fmt.Errorf("bootstrap projector requires a SQL database")
	}

	projectorQueue := postgres.NewProjectorQueue(sqlDB, "bootstrap-index", time.Minute)
	reducerQueue := postgres.NewReducerQueue(sqlDB, "bootstrap-index", time.Minute)
	runtime := projector.Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: postgres.NewContentWriter(sqlDB),
		IntentWriter:  reducerQueue,
	}

	return projectorDeps{
		workSource: projectorQueue,
		factStore:  postgres.NewFactStore(sqlDB),
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
	defer session.Close(ctx)

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
