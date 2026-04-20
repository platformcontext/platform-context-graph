package main

import (
	"context"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/query"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
)

const reducerNeo4jCloseTimeout = 10 * time.Second

// cypherRunner is the narrow interface shared by both executor adapters.
type cypherRunner interface {
	RunCypher(ctx context.Context, cypher string, params map[string]any) error
	RunCypherGroup(ctx context.Context, stmts []sourceneo4j.Statement) error
}

// reducerNeo4jExecutor adapts a cypherRunner to the sourceneo4j.Executor
// interface used by EdgeWriter.
type reducerNeo4jExecutor struct {
	session cypherRunner
}

func (e reducerNeo4jExecutor) Execute(ctx context.Context, stmt sourceneo4j.Statement) error {
	return executeReducerCypherWithRetry(ctx, e.session, stmt)
}

// ExecuteGroup runs all statements in a single Neo4j transaction with
// automatic retry on transient errors (deadlocks, leader switches).
func (e reducerNeo4jExecutor) ExecuteGroup(ctx context.Context, stmts []sourceneo4j.Statement) error {
	return e.session.RunCypherGroup(ctx, stmts)
}

// reducerCypherExecutor adapts a cypherRunner to the reducer.CypherExecutor
// interface used by WorkloadMaterializer.
type reducerCypherExecutor struct {
	session cypherRunner
}

func (e reducerCypherExecutor) ExecuteCypher(ctx context.Context, cypher string, params map[string]any) error {
	return executeReducerCypherWithRetry(ctx, e.session, sourceneo4j.Statement{
		Operation:  sourceneo4j.OperationCanonicalUpsert,
		Cypher:     cypher,
		Parameters: params,
	})
}

type cypherRunnerStatementExecutor struct {
	runner cypherRunner
}

func (e cypherRunnerStatementExecutor) Execute(ctx context.Context, stmt sourceneo4j.Statement) error {
	return e.runner.RunCypher(ctx, stmt.Cypher, stmt.Parameters)
}

func executeReducerCypherWithRetry(
	ctx context.Context,
	runner cypherRunner,
	stmt sourceneo4j.Statement,
) error {
	retrying := sourceneo4j.RetryingExecutor{
		Inner: cypherRunnerStatementExecutor{runner: runner},
	}
	return retrying.Execute(ctx, stmt)
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
	defer func() { _ = session.Close(ctx) }()

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
}

// RunCypherGroup executes multiple Cypher statements inside a single write
// transaction. session.ExecuteWrite automatically retries the entire function
// on transient errors (deadlocks, leader switches), giving us atomic
// retract+upsert with built-in resilience.
func (r neo4jSessionRunner) RunCypherGroup(ctx context.Context, stmts []sourceneo4j.Statement) error {
	if r.Driver == nil {
		return fmt.Errorf("neo4j driver is required")
	}
	if len(stmts) == 0 {
		return nil
	}

	session := r.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: r.DatabaseName,
	})
	defer func() { _ = session.Close(ctx) }()

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
	})
	return err
}

// QueryCypherExists runs a read-only Cypher query and returns true if at
// least one row is returned. This implements neo4j.CypherReader for the
// CanonicalNodeChecker pre-flight check.
func (r neo4jSessionRunner) QueryCypherExists(ctx context.Context, cypher string, params map[string]any) (bool, error) {
	if r.Driver == nil {
		return false, fmt.Errorf("neo4j driver is required")
	}

	session := r.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeRead,
		DatabaseName: r.DatabaseName,
	})
	defer func() { _ = session.Close(ctx) }()

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return false, err
	}
	hasNext := result.Next(ctx)
	if err := result.Err(); err != nil {
		return false, err
	}
	return hasNext, nil
}

// Run executes a read-only Cypher query and returns row maps. This implements
// query.GraphReader for reducer-local graph lookups.
func (r neo4jSessionRunner) Run(ctx context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
	if r.Driver == nil {
		return nil, fmt.Errorf("neo4j driver is required")
	}

	session := r.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeRead,
		DatabaseName: r.DatabaseName,
	})
	defer func() { _ = session.Close(ctx) }()

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return nil, err
	}
	records, err := result.Collect(ctx)
	if err != nil {
		return nil, err
	}

	rows := make([]map[string]any, 0, len(records))
	for _, record := range records {
		row := make(map[string]any, len(record.Keys))
		for i, key := range record.Keys {
			row[key] = record.Values[i]
		}
		rows = append(rows, row)
	}
	return rows, nil
}

// RunSingle executes a read-only Cypher query and returns the first row.
func (r neo4jSessionRunner) RunSingle(ctx context.Context, cypher string, params map[string]any) (map[string]any, error) {
	rows, err := r.Run(ctx, cypher, params)
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	return rows[0], nil
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

// openReducerNeo4jAdapters opens a Neo4j driver and returns the executor
// adapters needed by the reducer: one for EdgeWriter (sourceneo4j.Executor),
// one for WorkloadMaterializer (reducer.CypherExecutor), and one for
// pre-flight canonical node checks (sourceneo4j.CypherReader).
func openReducerNeo4jAdapters(
	parent context.Context,
	getenv func(string) string,
) (sourceneo4j.Executor, reducer.CypherExecutor, sourceneo4j.CypherReader, query.GraphReader, io.Closer, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, nil, nil, nil, err
	}

	runner := neo4jSessionRunner{
		Driver:       driver,
		DatabaseName: cfg.DatabaseName,
	}

	return reducerNeo4jExecutor{session: runner},
		reducerCypherExecutor{session: runner},
		runner,
		runner,
		reducerNeo4jDriverCloser{Driver: driver},
		nil
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
