package main

import (
	"context"
	"fmt"
	"io"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
)

const reducerNeo4jCloseTimeout = 10 * time.Second

// cypherRunner is the narrow interface shared by both executor adapters.
type cypherRunner interface {
	RunCypher(ctx context.Context, cypher string, params map[string]any) error
}

// reducerNeo4jExecutor adapts a cypherRunner to the sourceneo4j.Executor
// interface used by EdgeWriter.
type reducerNeo4jExecutor struct {
	session cypherRunner
}

func (e reducerNeo4jExecutor) Execute(ctx context.Context, stmt sourceneo4j.Statement) error {
	return e.session.RunCypher(ctx, stmt.Cypher, stmt.Parameters)
}

// reducerCypherExecutor adapts a cypherRunner to the reducer.CypherExecutor
// interface used by WorkloadMaterializer.
type reducerCypherExecutor struct {
	session cypherRunner
}

func (e reducerCypherExecutor) ExecuteCypher(ctx context.Context, cypher string, params map[string]any) error {
	return e.session.RunCypher(ctx, cypher, params)
}

// neo4jSessionRunner wraps a Neo4j driver into the cypherRunner interface,
// opening a write session per call.
type neo4jSessionRunner struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
}

func (r neo4jSessionRunner) RunCypher(ctx context.Context, cypher string, params map[string]any) error {
	if r.Driver == nil {
		return fmt.Errorf("neo4j driver is required")
	}

	session := r.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: r.DatabaseName,
	})
	defer session.Close(ctx)

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
}

// reducerNeo4jDriverCloser wraps driver close with a timeout.
type reducerNeo4jDriverCloser struct {
	Driver neo4jdriver.DriverWithContext
}

func (c reducerNeo4jDriverCloser) Close() error {
	if c.Driver == nil {
		return nil
	}
	closeCtx, cancel := context.WithTimeout(context.Background(), reducerNeo4jCloseTimeout)
	defer cancel()
	return c.Driver.Close(closeCtx)
}

// openReducerNeo4jAdapters opens a Neo4j driver and returns both executor
// adapters needed by the reducer: one for EdgeWriter (sourceneo4j.Executor)
// and one for WorkloadMaterializer (reducer.CypherExecutor).
func openReducerNeo4jAdapters(
	parent context.Context,
	getenv func(string) string,
) (sourceneo4j.Executor, reducer.CypherExecutor, io.Closer, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, nil, err
	}

	runner := neo4jSessionRunner{
		Driver:       driver,
		DatabaseName: cfg.DatabaseName,
	}

	return reducerNeo4jExecutor{session: runner},
		reducerCypherExecutor{session: runner},
		reducerNeo4jDriverCloser{Driver: driver},
		nil
}
