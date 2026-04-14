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
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const (
	ingesterCollectorPollInterval = time.Second
	ingesterConnectionTimeout     = 10 * time.Second
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
	graphWriter graph.Writer,
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

	projectorSvc, err := buildIngesterProjectorService(database, graphWriter, getenv, tracer, instruments, logger)
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
	graphWriter graph.Writer,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (projector.Service, error) {
	projectorQueue := postgres.NewProjectorQueue(database, "ingester", time.Minute)
	reducerQueue := postgres.NewReducerQueue(database, "ingester", time.Minute)
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

	return projector.Service{
		PollInterval: time.Second,
		WorkSource:   projectorQueue,
		FactStore:    postgres.NewFactStore(database),
		Runner:       buildIngesterProjectorRuntime(database, graphWriter, reducerQueue, retryInjector, tracer, instruments),
		WorkSink:     projectorQueue,
		Tracer:       tracer,
		Instruments:  instruments,
		Logger:       logger,
		Workers:      projectorWorkerCount(getenv),
	}, nil
}

func projectorWorkerCount(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_PROJECTOR_WORKERS")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	n := runtime.NumCPU()
	if n > 4 {
		n = 4
	}
	if n < 1 {
		n = 1
	}
	return n
}

func buildIngesterProjectorRuntime(
	database postgres.ExecQueryer,
	graphWriter graph.Writer,
	intentWriter projector.ReducerIntentWriter,
	retryInjector projector.RetryInjector,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) projector.Runtime {
	return projector.Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: postgres.NewContentWriter(database),
		IntentWriter:  intentWriter,
		RetryInjector: retryInjector,
		Tracer:        tracer,
		Instruments:   instruments,
	}
}

func openIngesterGraphWriter(
	parent context.Context,
	getenv func(string) string,
) (graph.Writer, io.Closer, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, err
	}

	return sourceneo4j.Adapter{
			Executor: ingesterNeo4jExecutor{
				Driver:       driver,
				DatabaseName: cfg.DatabaseName,
			},
		},
		ingesterNeo4jDriverCloser{Driver: driver},
		nil
}

type ingesterNeo4jExecutor struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
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

	result, err := session.Run(ctx, statement.Cypher, statement.Parameters)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
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
