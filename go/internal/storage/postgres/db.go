package postgres

import (
	"context"
	"database/sql"
)

// ExecQueryer combines read and write access for storage adapters.
type ExecQueryer interface {
	Queryer
	Executor
}

// SQLDB adapts a *sql.DB into the combined storage interface surface.
type SQLDB struct {
	DB *sql.DB
}

// QueryContext implements Queryer against a sql.DB.
func (db SQLDB) QueryContext(ctx context.Context, query string, args ...any) (Rows, error) {
	return db.DB.QueryContext(ctx, query, args...)
}

// ExecContext implements Executor against a sql.DB.
func (db SQLDB) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	return db.DB.ExecContext(ctx, query, args...)
}
