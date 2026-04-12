package main

import (
	"context"
	"database/sql"
	"errors"
	"testing"
)

func TestRunAppliesBootstrapSchemaAndClosesDatabase(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{}
	opened := false
	applied := false

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			opened = true
			return db, nil
		},
		func(ctx context.Context, exec bootstrapExecutor) error {
			applied = true
			if exec != db {
				t.Fatalf("apply exec = %T, want fakeBootstrapDB", exec)
			}
			_, _ = exec.ExecContext(ctx, "SELECT 1")
			return nil
		},
	)
	if err != nil {
		t.Fatalf("run() error = %v, want nil", err)
	}
	if !opened {
		t.Fatal("run() did not open bootstrap database")
	}
	if !applied {
		t.Fatal("run() did not apply bootstrap schema")
	}
	if !db.closed {
		t.Fatal("run() did not close bootstrap database")
	}
	if db.execCalls != 1 {
		t.Fatalf("ExecContext() calls = %d, want 1", db.execCalls)
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
