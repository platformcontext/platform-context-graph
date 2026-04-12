package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatal(err)
	}
}

func run(parent context.Context) error {
	db, err := openReducerDB()
	if err != nil {
		return err
	}
	defer db.Close()

	serviceRunner, err := buildReducerService(postgres.SQLDB{DB: db})
	if err != nil {
		return err
	}
	service, err := app.NewHosted("reducer", serviceRunner)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}

func buildReducerService(database postgres.SQLDB) (reducer.Service, error) {
	registry := reducer.NewRegistry()
	for _, def := range reducer.DefaultDomainDefinitions() {
		def.Handler = reducer.HandlerFunc(func(context.Context, reducer.Intent) (reducer.Result, error) {
			return reducer.Result{
				Status:          reducer.ResultStatusSucceeded,
				EvidenceSummary: "placeholder reducer handler",
			}, nil
		})
		if err := registry.Register(def); err != nil {
			return reducer.Service{}, err
		}
	}

	executor, err := reducer.NewRuntime(registry)
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

func openReducerDB() (*sql.DB, error) {
	dsn := strings.TrimSpace(
		firstEnvValue("PCG_FACT_STORE_DSN", "PCG_CONTENT_STORE_DSN", "PCG_POSTGRES_DSN"),
	)
	if dsn == "" {
		return nil, fmt.Errorf("set PCG_FACT_STORE_DSN, PCG_CONTENT_STORE_DSN, or PCG_POSTGRES_DSN")
	}

	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, fmt.Errorf("open postgres connection: %w", err)
	}
	if err := db.PingContext(context.Background()); err != nil {
		db.Close()
		return nil, fmt.Errorf("ping postgres: %w", err)
	}

	return db, nil
}

func firstEnvValue(keys ...string) string {
	for _, key := range keys {
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			return value
		}
	}

	return ""
}
