package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatal(err)
	}
}

func run(parent context.Context) error {
	db, err := runtimecfg.OpenPostgres(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer db.Close()

	neo4jExecutor, cypherExecutor, neo4jCloser, err := openReducerNeo4jAdapters(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer neo4jCloser.Close()

	serviceRunner, err := buildReducerService(postgres.SQLDB{DB: db}, neo4jExecutor, cypherExecutor, os.Getenv)
	if err != nil {
		return err
	}
	retryPolicy, err := loadReducerQueueConfig(os.Getenv)
	if err != nil {
		return err
	}
	statusReader := statuspkg.WithRetryPolicies(
		postgres.NewStatusStore(postgres.SQLQueryer{DB: db}),
		statuspkg.MergeRetryPolicies(
			statuspkg.DefaultRetryPolicies(),
			statuspkg.RetryPolicySummary{
				Stage:       "reducer",
				MaxAttempts: retryPolicy.MaxAttempts,
				RetryDelay:  retryPolicy.RetryDelay,
			},
		)...,
	)
	service, err := app.NewHostedWithStatusServer(
		"reducer",
		serviceRunner,
		statusReader,
	)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}

func buildReducerService(
	database postgres.ExecQueryer,
	neo4jExec sourceneo4j.Executor,
	cypherExec reducer.CypherExecutor,
	getenv func(string) string,
) (reducer.Service, error) {
	executor, err := reducer.NewDefaultRuntime(reducer.DefaultHandlers{
		WorkloadIdentityWriter:        reducer.PostgresWorkloadIdentityWriter{DB: database},
		CloudAssetResolutionWriter:    reducer.PostgresCloudAssetResolutionWriter{DB: database},
		PlatformMaterializationWriter: reducer.PostgresPlatformMaterializationWriter{DB: database},
		WorkloadMaterializer:          reducer.NewWorkloadMaterializer(cypherExec),
	})
	if err != nil {
		return reducer.Service{}, err
	}

	edgeWriter := sourceneo4j.NewEdgeWriter(neo4jExec)

	retryCfg, err := loadReducerQueueConfig(getenv)
	if err != nil {
		return reducer.Service{}, err
	}
	workQueue := postgres.NewReducerQueue(database, "reducer", time.Minute)
	workQueue.RetryDelay = retryCfg.RetryDelay
	workQueue.MaxAttempts = retryCfg.MaxAttempts

	return reducer.Service{
		PollInterval:               time.Second,
		WorkSource:                 workQueue,
		Executor:                   executor,
		WorkSink:                   workQueue,
		SharedProjectionEdgeWriter: edgeWriter,
	}, nil
}
