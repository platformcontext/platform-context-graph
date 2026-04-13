package main

import (
	"context"
	"fmt"
	"io"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	pythonbridge "github.com/platformcontext/platform-context-graph/go/internal/compatibility/pythonbridge"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const (
	ingesterCollectorPollInterval  = time.Second
	ingesterConnectionTimeout      = 10 * time.Second
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
	database postgres.SQLDB,
	graphWriter graph.Writer,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
) (compositeRunner, error) {
	collectorSvc, err := buildIngesterCollectorService(database, getenv, getwd, environ)
	if err != nil {
		return compositeRunner{}, fmt.Errorf("build ingester collector: %w", err)
	}

	projectorSvc, err := buildIngesterProjectorService(database, graphWriter, getenv)
	if err != nil {
		return compositeRunner{}, fmt.Errorf("build ingester projector: %w", err)
	}

	return compositeRunner{runners: []app.Runner{collectorSvc, projectorSvc}}, nil
}

func buildIngesterCollectorService(
	database postgres.SQLDB,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
) (collector.Service, error) {
	repoRoot, err := resolveIngesterRepoRoot(getenv, getwd)
	if err != nil {
		return collector.Service{}, err
	}

	return collector.Service{
		Source: &collector.GitSource{
			Component: "ingester",
			Selector: pythonbridge.GitSelectionRunner{
				PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
				RepoRoot:         repoRoot,
				Env:              environ(),
			},
			Snapshotter: pythonbridge.GitRepositorySnapshotRunner{
				PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
				RepoRoot:         repoRoot,
				Env:              environ(),
			},
		},
		Committer:    postgres.NewIngestionStore(database),
		PollInterval: ingesterCollectorPollInterval,
	}, nil
}

func buildIngesterProjectorService(
	database postgres.SQLDB,
	graphWriter graph.Writer,
	getenv func(string) string,
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
		Runner:       buildIngesterProjectorRuntime(database, graphWriter, reducerQueue, retryInjector),
		WorkSink:     projectorQueue,
	}, nil
}

func buildIngesterProjectorRuntime(
	database postgres.SQLDB,
	graphWriter graph.Writer,
	intentWriter projector.ReducerIntentWriter,
	retryInjector projector.RetryInjector,
) projector.Runtime {
	return projector.Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: postgres.NewContentWriter(database),
		IntentWriter:  intentWriter,
		RetryInjector: retryInjector,
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
	defer session.Close(ctx)

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
