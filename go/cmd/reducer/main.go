package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func main() {
	if err := run(context.Background()); err != nil {
		slog.Error("reducer failed", "error", err)
		os.Exit(1)
	}
}

func run(parent context.Context) error {
	// Initialize telemetry
	bootstrap, err := telemetry.NewBootstrap("reducer")
	if err != nil {
		return fmt.Errorf("telemetry bootstrap: %w", err)
	}
	providers, err := telemetry.NewProviders(parent, bootstrap)
	if err != nil {
		return fmt.Errorf("telemetry providers: %w", err)
	}
	defer func() {
		_ = providers.Shutdown(context.Background())
	}()

	logger := telemetry.NewLogger(bootstrap, "reducer", "reducer")
	tracer := providers.TracerProvider.Tracer(telemetry.DefaultSignalName)
	meter := providers.MeterProvider.Meter(telemetry.DefaultSignalName)
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		return fmt.Errorf("telemetry instruments: %w", err)
	}

	logger.Info("starting reducer")

	db, err := runtimecfg.OpenPostgres(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()

	neo4jExecutor, cypherExecutor, neo4jCloser, err := openReducerNeo4jAdapters(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer func() { _ = neo4jCloser.Close() }()

	instrumentedDB := &postgres.InstrumentedDB{
		Inner:       postgres.SQLDB{DB: db},
		Tracer:      tracer,
		Instruments: instruments,
		StoreName:   "reducer",
	}
	instrumentedNeo4j := &sourceneo4j.InstrumentedExecutor{
		Inner:       neo4jExecutor,
		Tracer:      tracer,
		Instruments: instruments,
	}
	intentStore := postgres.NewSharedIntentStore(instrumentedDB)
	serviceRunner, err := buildReducerService(instrumentedDB, instrumentedNeo4j, cypherExecutor, intentStore, os.Getenv, tracer, instruments, logger)
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
		runtimecfg.WithPrometheusHandler(providers.PrometheusHandler),
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
	intentStore *postgres.SharedIntentStore,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (reducer.Service, error) {
	executor, err := reducer.NewDefaultRuntime(reducer.DefaultHandlers{
		WorkloadIdentityWriter:             reducer.PostgresWorkloadIdentityWriter{DB: database},
		CloudAssetResolutionWriter:         reducer.PostgresCloudAssetResolutionWriter{DB: database},
		PlatformMaterializationWriter:      reducer.PostgresPlatformMaterializationWriter{DB: database},
		WorkloadMaterializer:               reducer.NewWorkloadMaterializer(cypherExec),
		InfrastructurePlatformMaterializer: reducer.NewInfrastructurePlatformMaterializer(cypherExec),
		FactLoader:                         postgres.NewFactStore(database),
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
		SharedProjectionRunner: &reducer.SharedProjectionRunner{
			IntentReader: intentStore,
			LeaseManager: intentStore,
			EdgeWriter:   edgeWriter,
			AcceptedGen:  postgres.NewAcceptedGenerationLookup(database),
			Tracer:       tracer,
			Instruments:  instruments,
			Logger:       logger,
		},
		Tracer:      tracer,
		Instruments: instruments,
		Logger:      logger,
	}, nil
}
