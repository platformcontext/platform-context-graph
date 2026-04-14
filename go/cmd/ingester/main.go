package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	_ "github.com/jackc/pgx/v5/stdlib"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/recovery"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func main() {
	if err := run(context.Background()); err != nil {
		slog.Error("ingester failed", "error", err)
		os.Exit(1)
	}
}

func run(parent context.Context) error {
	// Initialize telemetry
	bootstrap, err := telemetry.NewBootstrap("ingester")
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

	logger := telemetry.NewLogger(bootstrap, "collector", "ingester")
	tracer := providers.TracerProvider.Tracer(telemetry.DefaultSignalName)
	meter := providers.MeterProvider.Meter(telemetry.DefaultSignalName)
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		return fmt.Errorf("telemetry instruments: %w", err)
	}

	logger.Info("starting ingester")

	db, err := runtimecfg.OpenPostgres(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer func() {
		_ = db.Close()
	}()

	graphWriter, graphCloser, err := openIngesterGraphWriter(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer func() {
		_ = graphCloser.Close()
	}()

	instrumentedDB := &postgres.InstrumentedDB{
		Inner:       postgres.SQLDB{DB: db},
		Tracer:      tracer,
		Instruments: instruments,
		StoreName:   "ingester",
	}

	runner, err := buildIngesterService(
		instrumentedDB,
		graphWriter,
		os.Getenv,
		os.Getwd,
		os.Environ,
		tracer,
		instruments,
		logger,
	)
	if err != nil {
		return err
	}

	retryPolicy, err := loadIngesterRetryPolicy(os.Getenv)
	if err != nil {
		return err
	}
	statusReader := statuspkg.WithRetryPolicies(
		postgres.NewStatusStore(postgres.SQLQueryer{DB: db}),
		statuspkg.MergeRetryPolicies(
			statuspkg.DefaultRetryPolicies(),
			statuspkg.RetryPolicySummary{
				Stage:       "projector",
				MaxAttempts: retryPolicy.MaxAttempts,
				RetryDelay:  retryPolicy.RetryDelay,
			},
		)...,
	)

	recoveryStore := postgres.NewRecoveryStore(postgres.SQLDB{DB: db})
	recoveryHandler, err := recovery.NewHandler(recoveryStore)
	if err != nil {
		return err
	}
	httpRecovery, err := runtimecfg.NewRecoveryHandler(recoveryHandler)
	if err != nil {
		return err
	}

	service, err := app.NewHostedWithStatusServer(
		"ingester", runner, statusReader,
		runtimecfg.WithRecoveryHandler(httpRecovery),
		runtimecfg.WithPrometheusHandler(providers.PrometheusHandler),
	)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}
