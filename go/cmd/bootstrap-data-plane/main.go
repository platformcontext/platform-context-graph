package main

import (
	"context"
	"errors"
	"log"
	"os"

	_ "github.com/jackc/pgx/v5/stdlib"

	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

type bootstrapExecutor interface {
	postgres.Executor
}

type bootstrapDB interface {
	bootstrapExecutor
	Close() error
}

type openBootstrapDBFn func(context.Context, func(string) string) (bootstrapDB, error)
type applyBootstrapFn func(context.Context, bootstrapExecutor) error

func main() {
	if err := run(
		context.Background(),
		os.Getenv,
		openBootstrapDB,
		func(ctx context.Context, exec bootstrapExecutor) error {
			return postgres.ApplyBootstrap(ctx, exec)
		},
	); err != nil {
		log.Fatal(err)
	}
}

func run(
	ctx context.Context,
	getenv func(string) string,
	openFn openBootstrapDBFn,
	applyFn applyBootstrapFn,
) (err error) {
	db, err := openFn(ctx, getenv)
	if err != nil {
		return err
	}

	defer func() {
		if closeErr := db.Close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	if err = applyFn(ctx, db); err != nil {
		return err
	}

	return nil
}

func openBootstrapDB(ctx context.Context, getenv func(string) string) (bootstrapDB, error) {
	return runtimecfg.OpenPostgres(ctx, getenv)
}
