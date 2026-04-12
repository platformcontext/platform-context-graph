package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	_ "github.com/jackc/pgx/v5/stdlib"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
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

	graphWriter, graphCloser, err := openProjectorGraphWriter(parent, os.Getenv)
	if err != nil {
		return err
	}
	defer graphCloser.Close()

	runner := buildProjectorService(postgres.SQLDB{DB: db}, graphWriter)
	service, err := app.NewHosted("projector", runner)
	if err != nil {
		return err
	}
	adminServer, err := runtimecfg.NewStatusAdminServer(
		service.Config,
		postgres.NewStatusStore(postgres.SQLQueryer{DB: db}),
	)
	if err != nil {
		return err
	}
	service.Lifecycle = app.ComposeLifecycles(service.Lifecycle, adminServer)

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}
