package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"

	_ "github.com/jackc/pgx/v5/stdlib"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

type bootstrapDB interface {
	Close() error
}

type graphDeps struct {
	writer graph.Writer
	close  func() error
}

type collectorDeps struct {
	source    collector.Source
	committer collector.Committer
}

type projectorDeps struct {
	workSource projector.ProjectorWorkSource
	factStore  projector.FactStore
	runner     projector.ProjectionRunner
	workSink   projector.ProjectorWorkSink
}

type openBootstrapDBFn func(context.Context, func(string) string) (bootstrapDB, error)
type applyBootstrapFn func(context.Context, bootstrapDB) error
type openGraphFn func(context.Context, func(string) string) (graphDeps, error)
type buildCollectorFn func(context.Context, bootstrapDB, func(string) string) (collectorDeps, error)
type buildProjectorFn func(context.Context, bootstrapDB, graph.Writer, func(string) string) (projectorDeps, error)

func main() {
	if err := run(
		context.Background(),
		os.Getenv,
		openBootstrapDB,
		applySchema,
		openBootstrapGraph,
		buildBootstrapCollector,
		buildBootstrapProjector,
	); err != nil {
		log.Fatal(err)
	}
}

func run(
	ctx context.Context,
	getenv func(string) string,
	openDBFn openBootstrapDBFn,
	schemaFn applyBootstrapFn,
	graphFn openGraphFn,
	collectorFn buildCollectorFn,
	projectorFn buildProjectorFn,
) (err error) {
	db, err := openDBFn(ctx, getenv)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := db.Close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	if err = schemaFn(ctx, db); err != nil {
		return err
	}

	gd, err := graphFn(ctx, getenv)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := gd.close(); closeErr != nil {
			err = errors.Join(err, closeErr)
		}
	}()

	cd, err := collectorFn(ctx, db, getenv)
	if err != nil {
		return err
	}

	if err = drainCollector(ctx, cd.source, cd.committer); err != nil {
		return err
	}

	pd, err := projectorFn(ctx, db, gd.writer, getenv)
	if err != nil {
		return err
	}

	return drainProjector(ctx, pd.workSource, pd.factStore, pd.runner, pd.workSink)
}

// drainCollector runs the collector source until no more work is available.
func drainCollector(ctx context.Context, source collector.Source, committer collector.Committer) error {
	for {
		collected, ok, err := source.Next(ctx)
		if err != nil {
			return fmt.Errorf("bootstrap collector: %w", err)
		}
		if !ok {
			return nil
		}

		if err := committer.CommitScopeGeneration(
			ctx,
			collected.Scope,
			collected.Generation,
			collected.Facts,
		); err != nil {
			return fmt.Errorf("bootstrap collector commit: %w", err)
		}
	}
}

// drainProjector runs the projector until no more work is available.
func drainProjector(
	ctx context.Context,
	workSource projector.ProjectorWorkSource,
	factStore projector.FactStore,
	runner projector.ProjectionRunner,
	workSink projector.ProjectorWorkSink,
) error {
	for {
		work, ok, err := workSource.Claim(ctx)
		if err != nil {
			return fmt.Errorf("bootstrap projector claim: %w", err)
		}
		if !ok {
			return nil
		}

		factsForGeneration, err := factStore.LoadFacts(ctx, work)
		if err != nil {
			return fmt.Errorf("bootstrap projector load facts: %w", err)
		}

		result, err := runner.Project(ctx, work.Scope, work.Generation, factsForGeneration)
		if err != nil {
			return fmt.Errorf("bootstrap projector project: %w", err)
		}

		if err := workSink.Ack(ctx, work, result); err != nil {
			return fmt.Errorf("bootstrap projector ack: %w", err)
		}
	}
}

func openBootstrapDB(ctx context.Context, getenv func(string) string) (bootstrapDB, error) {
	return runtimecfg.OpenPostgres(ctx, getenv)
}

func applySchema(ctx context.Context, db bootstrapDB) error {
	exec, ok := db.(postgres.Executor)
	if !ok {
		return fmt.Errorf("bootstrap database does not support schema execution")
	}
	return postgres.ApplyBootstrap(ctx, exec)
}

func openBootstrapGraph(ctx context.Context, getenv func(string) string) (graphDeps, error) {
	writer, closer, err := openBootstrapGraphWriter(ctx, getenv)
	if err != nil {
		return graphDeps{}, err
	}
	return graphDeps{writer: writer, close: closer.Close}, nil
}
