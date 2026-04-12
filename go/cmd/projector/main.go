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
	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatal(err)
	}
}

func run(parent context.Context) error {
	db, err := openProjectorDB()
	if err != nil {
		return err
	}
	defer db.Close()

	runner := buildProjectorService(postgres.SQLDB{DB: db})
	service, err := app.NewHosted("projector", runner)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}

func buildProjectorService(database postgres.SQLDB) projector.Service {
	projectorQueue := postgres.NewProjectorQueue(database, "projector", time.Minute)
	reducerQueue := postgres.NewReducerQueue(database, "projector", time.Minute)

	return projector.Service{
		PollInterval: time.Second,
		WorkSource:   projectorQueue,
		FactStore:    postgres.NewFactStore(database),
		Runner: projector.Runtime{
			GraphWriter:   &graph.MemoryWriter{},
			ContentWriter: &content.MemoryWriter{},
			IntentWriter:  reducerQueue,
		},
		WorkSink: projectorQueue,
	}
}

func openProjectorDB() (*sql.DB, error) {
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
