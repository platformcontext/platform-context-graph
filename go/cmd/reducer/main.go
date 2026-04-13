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

	serviceRunner, err := buildReducerService(postgres.SQLDB{DB: db})
	if err != nil {
		return err
	}
	service, err := app.NewHostedWithStatusServer(
		"reducer",
		serviceRunner,
		postgres.NewStatusStore(postgres.SQLQueryer{DB: db}),
	)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}

func buildReducerService(database postgres.ExecQueryer) (reducer.Service, error) {
	executor, err := reducer.NewDefaultRuntime(reducer.DefaultHandlers{
		WorkloadIdentityWriter: reducer.PostgresWorkloadIdentityWriter{DB: database},
	})
	if err != nil {
		return reducer.Service{}, err
	}
	workQueue := postgres.NewReducerQueue(database, "reducer", time.Minute)

	return reducer.Service{
		PollInterval: time.Second,
		WorkSource:   workQueue,
		Executor:     executor,
		WorkSink:     workQueue,
	}, nil
}
