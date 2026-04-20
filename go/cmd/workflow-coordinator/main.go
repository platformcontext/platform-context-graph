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
	"github.com/platformcontext/platform-context-graph/go/internal/coordinator"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func main() {
	if err := run(context.Background()); err != nil {
		slog.Error("workflow coordinator failed", "error", err)
		os.Exit(1)
	}
}

func run(parent context.Context) error {
	bootstrap, err := telemetry.NewBootstrap("workflow-coordinator")
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

	logger := telemetry.NewLogger(bootstrap, "workflow-coordinator", "workflow-coordinator")

	db, err := runtimecfg.OpenPostgres(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()

	cfg, err := coordinator.LoadConfig(os.Getenv)
	if err != nil {
		return err
	}

	metrics, err := coordinator.NewMetrics(providers.MeterProvider.Meter(telemetry.DefaultSignalName))
	if err != nil {
		return fmt.Errorf("coordinator metrics: %w", err)
	}

	store := postgres.NewWorkflowControlStore(postgres.SQLDB{DB: db})
	serviceRunner := coordinator.Service{
		Config:  cfg,
		Store:   store,
		Metrics: metrics,
		Logger:  logger,
	}
	statusReader := postgres.NewStatusStore(postgres.SQLQueryer{DB: db})
	service, err := app.NewHostedWithStatusServer(
		"workflow-coordinator",
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
