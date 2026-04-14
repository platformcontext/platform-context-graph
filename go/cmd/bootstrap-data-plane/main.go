package main

import (
	"context"
	"errors"
	"log"
	"log/slog"
	"os"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

type bootstrapExecutor interface {
	postgres.Executor
}

type bootstrapDB interface {
	bootstrapExecutor
	Close() error
}

type neo4jDeps struct {
	executor graph.CypherExecutor
	close    func() error
}

type openBootstrapDBFn func(context.Context, func(string) string) (bootstrapDB, error)
type applyPostgresFn func(context.Context, bootstrapExecutor) error
type openNeo4jFn func(context.Context, func(string) string) (neo4jDeps, error)
type applyNeo4jFn func(context.Context, graph.CypherExecutor, *slog.Logger) error

func main() {
	if err := run(
		context.Background(),
		os.Getenv,
		openBootstrapDB,
		func(ctx context.Context, exec bootstrapExecutor) error {
			return postgres.ApplyBootstrap(ctx, exec)
		},
		openNeo4j,
		graph.EnsureSchema,
	); err != nil {
		log.Fatal(err)
	}
}

func run(
	ctx context.Context,
	getenv func(string) string,
	openDBFn openBootstrapDBFn,
	applyPgFn applyPostgresFn,
	openNeo4jFn openNeo4jFn,
	applyNeo4jFn applyNeo4jFn,
) (err error) {
	logger := slog.Default()
	logger.Info("starting data-plane schema migration")

	// Postgres schema
	db, err := openDBFn(ctx, getenv)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := db.Close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	if err = applyPgFn(ctx, db); err != nil {
		return err
	}
	logger.Info("postgres schema applied")

	// Neo4j schema
	nd, err := openNeo4jFn(ctx, getenv)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := nd.close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	if err = applyNeo4jFn(ctx, nd.executor, logger); err != nil {
		return err
	}
	logger.Info("neo4j schema applied")

	return nil
}

func openBootstrapDB(ctx context.Context, getenv func(string) string) (bootstrapDB, error) {
	return runtimecfg.OpenPostgres(ctx, getenv)
}

const neo4jCloseTimeout = 10 * time.Second

func openNeo4j(ctx context.Context, getenv func(string) string) (neo4jDeps, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(ctx, getenv)
	if err != nil {
		return neo4jDeps{}, err
	}

	return neo4jDeps{
		executor: &neo4jSchemaExecutor{
			driver:       driver,
			databaseName: cfg.DatabaseName,
		},
		close: func() error {
			closeCtx, cancel := context.WithTimeout(context.Background(), neo4jCloseTimeout)
			defer cancel()
			return driver.Close(closeCtx)
		},
	}, nil
}

// neo4jSchemaExecutor adapts the Neo4j driver to the graph.CypherExecutor
// interface for schema DDL execution.
type neo4jSchemaExecutor struct {
	driver       neo4jdriver.DriverWithContext
	databaseName string
}

func (e *neo4jSchemaExecutor) ExecuteCypher(ctx context.Context, stmt graph.CypherStatement) error {
	session := e.driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: e.databaseName,
	})
	defer func() {
		_ = session.Close(ctx)
	}()

	result, err := session.Run(ctx, stmt.Cypher, stmt.Parameters)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
}
