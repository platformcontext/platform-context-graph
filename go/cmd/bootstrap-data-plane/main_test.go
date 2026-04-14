package main

import (
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
)

func noopNeo4j(_ context.Context, _ func(string) string) (neo4jDeps, error) {
	return neo4jDeps{
		executor: &fakeNeo4jExecutor{},
		close:    func() error { return nil },
	}, nil
}

func noopApplyNeo4j(_ context.Context, _ graph.CypherExecutor, _ *slog.Logger) error {
	return nil
}

func TestRunAppliesPostgresAndNeo4jSchemas(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{}
	pgApplied := false
	neo4jApplied := false

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return db, nil
		},
		func(ctx context.Context, exec bootstrapExecutor) error {
			pgApplied = true
			if exec != db {
				t.Fatalf("apply exec = %T, want fakeBootstrapDB", exec)
			}
			_, _ = exec.ExecContext(ctx, "SELECT 1")
			return nil
		},
		noopNeo4j,
		func(_ context.Context, exec graph.CypherExecutor, _ *slog.Logger) error {
			neo4jApplied = true
			if exec == nil {
				t.Fatal("neo4j executor is nil")
			}
			return nil
		},
	)
	if err != nil {
		t.Fatalf("run() error = %v, want nil", err)
	}
	if !pgApplied {
		t.Fatal("run() did not apply postgres schema")
	}
	if !neo4jApplied {
		t.Fatal("run() did not apply neo4j schema")
	}
	if !db.closed {
		t.Fatal("run() did not close postgres database")
	}
}

func TestRunReturnsCloseErrorWhenBootstrapSucceeds(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{closeErr: errors.New("close failed")}

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return db, nil
		},
		func(context.Context, bootstrapExecutor) error {
			return nil
		},
		noopNeo4j,
		noopApplyNeo4j,
	)
	if err == nil {
		t.Fatal("run() error = nil, want non-nil")
	}
	if got := err.Error(); got != "close failed" {
		t.Fatalf("run() error = %q, want %q", got, "close failed")
	}
	if !db.closed {
		t.Fatal("run() did not close bootstrap database")
	}
}

func TestRunJoinsBootstrapAndCloseErrors(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{closeErr: errors.New("close failed")}
	bootstrapErr := errors.New("bootstrap failed")

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return db, nil
		},
		func(context.Context, bootstrapExecutor) error {
			return bootstrapErr
		},
		noopNeo4j,
		noopApplyNeo4j,
	)
	if err == nil {
		t.Fatal("run() error = nil, want non-nil")
	}
	if !errors.Is(err, bootstrapErr) {
		t.Fatalf("run() error does not include bootstrap error: %v", err)
	}
	if !errors.Is(err, db.closeErr) {
		t.Fatalf("run() error does not include close error: %v", err)
	}
	if !db.closed {
		t.Fatal("run() did not close bootstrap database")
	}
}

func TestRunReturnsNeo4jOpenError(t *testing.T) {
	t.Parallel()

	neo4jErr := errors.New("neo4j connection refused")

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return &fakeBootstrapDB{}, nil
		},
		func(context.Context, bootstrapExecutor) error {
			return nil
		},
		func(context.Context, func(string) string) (neo4jDeps, error) {
			return neo4jDeps{}, neo4jErr
		},
		noopApplyNeo4j,
	)
	if !errors.Is(err, neo4jErr) {
		t.Fatalf("run() error = %v, want %v", err, neo4jErr)
	}
}

func TestRunReturnsNeo4jSchemaError(t *testing.T) {
	t.Parallel()

	schemaErr := errors.New("neo4j schema failed")

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return &fakeBootstrapDB{}, nil
		},
		func(context.Context, bootstrapExecutor) error {
			return nil
		},
		noopNeo4j,
		func(_ context.Context, _ graph.CypherExecutor, _ *slog.Logger) error {
			return schemaErr
		},
	)
	if !errors.Is(err, schemaErr) {
		t.Fatalf("run() error = %v, want %v", err, schemaErr)
	}
}

func TestRunJoinsNeo4jCloseError(t *testing.T) {
	t.Parallel()

	closeErr := errors.New("neo4j close failed")

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return &fakeBootstrapDB{}, nil
		},
		func(context.Context, bootstrapExecutor) error {
			return nil
		},
		func(context.Context, func(string) string) (neo4jDeps, error) {
			return neo4jDeps{
				executor: &fakeNeo4jExecutor{},
				close:    func() error { return closeErr },
			}, nil
		},
		noopApplyNeo4j,
	)
	if !errors.Is(err, closeErr) {
		t.Fatalf("run() error = %v, want neo4j close error", err)
	}
}

type fakeBootstrapDB struct {
	execCalls int
	closed    bool
	closeErr  error
}

func (f *fakeBootstrapDB) ExecContext(
	context.Context,
	string,
	...any,
) (sql.Result, error) {
	f.execCalls++
	return fakeBootstrapResult{}, nil
}

func (f *fakeBootstrapDB) Close() error {
	f.closed = true
	return f.closeErr
}

type fakeBootstrapResult struct{}

func (fakeBootstrapResult) LastInsertId() (int64, error) { return 0, nil }
func (fakeBootstrapResult) RowsAffected() (int64, error) { return 0, nil }

type fakeNeo4jExecutor struct {
	calls int
}

func (f *fakeNeo4jExecutor) ExecuteCypher(_ context.Context, _ graph.CypherStatement) error {
	f.calls++
	return nil
}
