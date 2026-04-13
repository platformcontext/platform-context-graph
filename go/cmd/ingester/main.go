package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	_ "github.com/jackc/pgx/v5/stdlib"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/recovery"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
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

	graphWriter, graphCloser, err := openIngesterGraphWriter(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer graphCloser.Close()

	runner, err := buildIngesterService(
		postgres.SQLDB{DB: db},
		graphWriter,
		os.Getenv,
		os.Getwd,
		os.Environ,
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
	)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}
