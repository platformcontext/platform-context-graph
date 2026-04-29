package main

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"

	pgstorage "github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const deferredContentSearchIndexPollInterval = 2 * time.Second
const deferredContentSearchIndexBuildTimeout = 10 * time.Minute

type localContentSearchIndexDB interface {
	pgstorage.Executor
	QueryRowContext(context.Context, string, ...any) *sql.Row
}

// startDeferredContentSearchIndexes restores expensive content search indexes
// after the first local-authoritative queue drain.
func startDeferredContentSearchIndexes(ctx context.Context, dsn string) (func() error, error) {
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, fmt.Errorf("open deferred content search index connection: %w", err)
	}
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ping deferred content search index connection: %w", err)
	}

	maintainerCtx, cancel := context.WithCancel(ctx)
	done := make(chan error, 1)
	go func() {
		defer func() { _ = db.Close() }()
		done <- runDeferredContentSearchIndexes(maintainerCtx, db, deferredContentSearchIndexPollInterval)
	}()

	return func() error {
		cancel()
		err := <-done
		if err == nil || err == context.Canceled {
			return nil
		}
		return err
	}, nil
}

func runDeferredContentSearchIndexes(ctx context.Context, db localContentSearchIndexDB, interval time.Duration) error {
	if interval <= 0 {
		interval = deferredContentSearchIndexPollInterval
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		ready, err := localContentSearchIndexesReady(ctx, db)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: deferred content search index readiness check failed: %v\n", err)
		}
		if ready {
			start := time.Now()
			buildCtx, cancel := context.WithTimeout(context.Background(), deferredContentSearchIndexBuildTimeout)
			err := pgstorage.EnsureContentSearchIndexes(buildCtx, db)
			cancel()
			if err != nil {
				return err
			}
			fmt.Fprintf(os.Stderr, "deferred content search indexes ready duration=%s\n", time.Since(start).Round(time.Millisecond))
			return nil
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func localContentSearchIndexesReady(ctx context.Context, db localContentSearchIndexDB) (bool, error) {
	const query = `
SELECT
  (SELECT count(*) FROM fact_work_items) AS total_work,
  (SELECT count(*) FROM fact_work_items WHERE status <> 'succeeded') AS open_work,
  (SELECT count(*) FROM fact_work_items WHERE stage = 'projector' AND status = 'succeeded') AS completed_projector_work,
  (SELECT count(*) FROM shared_projection_intents WHERE completed_at IS NULL) AS open_shared_work
`
	var totalWork, openWork, completedProjectorWork, openSharedWork int
	if err := db.QueryRowContext(ctx, query).Scan(&totalWork, &openWork, &completedProjectorWork, &openSharedWork); err != nil {
		return false, fmt.Errorf("query local queue drain state: %w", err)
	}
	return totalWork > 0 && openWork == 0 && completedProjectorWork > 0 && openSharedWork == 0, nil
}
