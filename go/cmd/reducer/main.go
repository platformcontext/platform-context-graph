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

	queueObserver := postgres.NewQueueObserverStore(postgres.SQLQueryer{DB: db})
	if err := telemetry.RegisterObservableGauges(instruments, meter, queueObserver, nil); err != nil {
		return fmt.Errorf("register observable gauges: %w", err)
	}

	neo4jExecutor, cypherExecutor, neo4jReader, neo4jCloser, err := openReducerNeo4jAdapters(parent, os.Getenv)
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
	serviceRunner, err := buildReducerService(instrumentedDB, instrumentedNeo4j, cypherExecutor, intentStore, neo4jReader, os.Getenv, tracer, instruments, logger)
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
	neo4jReader sourceneo4j.CypherReader,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (reducer.Service, error) {
	sharedCfg := reducer.LoadSharedProjectionConfig(getenv)
	codeCallCfg := loadCodeCallProjectionConfig(getenv)
	repairCfg := loadGraphProjectionPhaseRepairConfig(getenv)
	codeCallEdgeBatchSize, codeCallEdgeGroupBatchSize := loadCodeCallEdgeWriterTuning(getenv)
	inheritanceEdgeGroupBatchSize, sqlRelationshipEdgeGroupBatchSize := loadSharedEdgeWriterGroupTuning(getenv)

	edgeWriterForHandlers := sourceneo4j.NewEdgeWriter(neo4jExec, neo4jBatchSize(getenv))
	edgeWriterForHandlers.Instruments = instruments
	edgeWriterForHandlers.InheritanceGroupBatchSize = inheritanceEdgeGroupBatchSize
	edgeWriterForHandlers.SQLRelationshipGroupBatchSize = sqlRelationshipEdgeGroupBatchSize
	relationshipStore := postgres.NewRelationshipStore(database)
	codeCallIntentWriter := postgres.NewCodeCallIntentWriterWithInstruments(database, instruments)
	acceptedGenerationPrefetch := postgres.NewAcceptedGenerationPrefetch(database)
	graphProjectionStateStore := postgres.NewGraphProjectionPhaseStateStore(database)
	graphProjectionRepairQueue := postgres.NewGraphProjectionPhaseRepairQueueStore(database)
	graphProjectionReadinessLookup := postgres.NewGraphProjectionReadinessLookup(database)
	graphProjectionReadinessPrefetch := postgres.NewGraphProjectionReadinessPrefetch(database)

	executor, err := reducer.NewDefaultRuntime(reducer.DefaultHandlers{
		WorkloadIdentityWriter:             reducer.PostgresWorkloadIdentityWriter{DB: database},
		CloudAssetResolutionWriter:         reducer.PostgresCloudAssetResolutionWriter{DB: database},
		PlatformMaterializationWriter:      reducer.PostgresPlatformMaterializationWriter{DB: database},
		WorkloadMaterializer:               reducer.NewWorkloadMaterializer(cypherExec),
		InfrastructurePlatformMaterializer: reducer.NewInfrastructurePlatformMaterializer(cypherExec),
		FactLoader:                         postgres.NewFactStore(database),
		CodeCallIntentWriter:               codeCallIntentWriter,
		GraphProjectionPhasePublisher:      graphProjectionStateStore,
		GraphProjectionRepairQueue:         graphProjectionRepairQueue,
		ReadinessLookup:                    graphProjectionReadinessLookup,
		ReadinessPrefetch:                  graphProjectionReadinessPrefetch,
		SemanticEntityWriter:               sourceneo4j.NewSemanticEntityWriter(neo4jExec, neo4jBatchSize(getenv)),
		SQLRelationshipEdgeWriter:          edgeWriterForHandlers,
		InheritanceEdgeWriter:              edgeWriterForHandlers,
		EvidenceFactLoader:                 relationshipStore,
		AssertionLoader:                    relationshipStore,
		ResolutionPersister:                relationshipStore,
		ResolvedRelationshipLoader:         relationshipStore,
		RepoDependencyEdgeWriter:           edgeWriterForHandlers,
		GenerationCheck:                    postgres.NewGenerationFreshnessCheck(database),
		Tracer:                             tracer,
		Instruments:                        instruments,
	})
	if err != nil {
		return reducer.Service{}, err
	}

	edgeWriter := sourceneo4j.NewEdgeWriter(neo4jExec, neo4jBatchSize(getenv))
	edgeWriter.Instruments = instruments
	edgeWriter.CodeCallBatchSize = codeCallEdgeBatchSize
	edgeWriter.CodeCallGroupBatchSize = codeCallEdgeGroupBatchSize
	edgeWriter.InheritanceGroupBatchSize = inheritanceEdgeGroupBatchSize
	edgeWriter.SQLRelationshipGroupBatchSize = sqlRelationshipEdgeGroupBatchSize

	retryCfg, err := loadReducerQueueConfig(getenv)
	if err != nil {
		return reducer.Service{}, err
	}
	workQueue := postgres.NewReducerQueue(database, "reducer", time.Minute)
	workQueue.RetryDelay = retryCfg.RetryDelay
	workQueue.MaxAttempts = retryCfg.MaxAttempts

	workers := loadReducerWorkerCount(getenv)
	return reducer.Service{
		PollInterval:               time.Second,
		WorkSource:                 workQueue,
		Executor:                   executor,
		WorkSink:                   workQueue,
		SharedProjectionEdgeWriter: edgeWriter,
		SharedProjectionRunner: &reducer.SharedProjectionRunner{
			IntentReader:        intentStore,
			LeaseManager:        intentStore,
			EdgeWriter:          edgeWriter,
			AcceptedGen:         postgres.NewAcceptedGenerationLookup(database),
			AcceptedGenPrefetch: acceptedGenerationPrefetch,
			ReadinessLookup:     graphProjectionReadinessLookup,
			ReadinessPrefetch:   graphProjectionReadinessPrefetch,
			Config:              sharedCfg,
			Tracer:              tracer,
			Instruments:         instruments,
			Logger:              logger,
		},
		CodeCallProjectionRunner: &reducer.CodeCallProjectionRunner{
			IntentReader:        intentStore,
			LeaseManager:        intentStore,
			EdgeWriter:          edgeWriter,
			AcceptedGen:         postgres.NewAcceptedGenerationLookup(database),
			AcceptedGenPrefetch: acceptedGenerationPrefetch,
			ReadinessLookup:     graphProjectionReadinessLookup,
			ReadinessPrefetch:   graphProjectionReadinessPrefetch,
			Config:              codeCallCfg,
			Tracer:              tracer,
			Instruments:         instruments,
			Logger:              logger,
		},
		GraphProjectionPhaseRepairer: &reducer.GraphProjectionPhaseRepairer{
			Queue:       graphProjectionRepairQueue,
			AcceptedGen: postgres.NewAcceptedGenerationLookup(database),
			StateLookup: graphProjectionStateStore,
			Publisher:   graphProjectionStateStore,
			Config:      repairCfg,
			Instruments: instruments,
			Logger:      logger,
		},
		Workers:        workers,
		BatchClaimSize: loadReducerBatchClaimSize(getenv, workers),
		Tracer:         tracer,
		Instruments:    instruments,
		Logger:         logger,
	}, nil
}
