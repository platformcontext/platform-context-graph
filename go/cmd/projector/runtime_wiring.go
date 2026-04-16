package main

import (
	"context"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const (
	projectorConnectionTimeout = 10 * time.Second
)

func buildProjectorService(
	database postgres.SQLDB,
	canonicalWriter projector.CanonicalWriter,
	getenv func(string) string,
) (projector.Service, error) {
	projectorQueue := postgres.NewProjectorQueue(database, "projector", time.Minute)
	reducerQueue := postgres.NewReducerQueue(database, "projector", time.Minute)
	retryInjector, err := loadProjectorRetryInjector(getenv)
	if err != nil {
		return projector.Service{}, err
	}
	retryPolicy, err := loadProjectorRetryPolicy(getenv)
	if err != nil {
		return projector.Service{}, err
	}
	projectorQueue.RetryDelay = retryPolicy.RetryDelay
	projectorQueue.MaxAttempts = retryPolicy.MaxAttempts

	return projector.Service{
		PollInterval: time.Second,
		WorkSource:   projectorQueue,
		FactStore:    postgres.NewFactStore(database),
		Runner:       buildProjectorRuntime(database, canonicalWriter, reducerQueue, retryInjector),
		WorkSink:     projectorQueue,
	}, nil
}

func buildProjectorRuntime(
	database postgres.SQLDB,
	canonicalWriter projector.CanonicalWriter,
	intentWriter projector.ReducerIntentWriter,
	retryInjector projector.RetryInjector,
) projector.Runtime {
	return projector.Runtime{
		CanonicalWriter: canonicalWriter,
		ContentWriter:   postgres.NewContentWriter(database),
		IntentWriter:    intentWriter,
		RetryInjector:   retryInjector,
	}
}

func openProjectorCanonicalWriter(
	parent context.Context,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
) (projector.CanonicalWriter, io.Closer, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, err
	}

	rawExecutor := projectorNeo4jExecutor{
		Driver:       driver,
		DatabaseName: cfg.DatabaseName,
	}

	instrumentedExecutor := &sourceneo4j.InstrumentedExecutor{
		Inner:       rawExecutor,
		Tracer:      tracer,
		Instruments: instruments,
	}

	return sourceneo4j.NewCanonicalNodeWriter(instrumentedExecutor, neo4jBatchSize(getenv), instruments),
		projectorNeo4jDriverCloser{Driver: driver},
		nil
}

type projectorNeo4jExecutor struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
}

func (e projectorNeo4jExecutor) Execute(ctx context.Context, statement sourceneo4j.Statement) error {
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

type projectorNeo4jDriverCloser struct {
	Driver neo4jdriver.DriverWithContext
}

func (c projectorNeo4jDriverCloser) Close() error {
	return closeProjectorNeo4jDriver(c.Driver)
}

func closeProjectorNeo4jDriver(driver neo4jdriver.DriverWithContext) error {
	if driver == nil {
		return nil
	}

	closeCtx, cancel := context.WithTimeout(context.Background(), projectorConnectionTimeout)
	defer cancel()
	return driver.Close(closeCtx)
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
