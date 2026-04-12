package content_test

import (
	"context"
	"database/sql"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	pg "github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestPostgresContentWriterUpsertsFileRowsAndDeletesTombstones(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC)
	db := &recordingExecQueryer{}
	writer := pg.NewContentWriter(db)
	writer.Now = func() time.Time { return now }

	result, err := writer.Write(context.Background(), content.Materialization{
		RepoID:       "repository:r_test",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		SourceSystem: "git",
		Records: []content.Record{
			{
				Path:   "schema.sql",
				Body:   "CREATE TABLE users (\n  id BIGINT\n);\n",
				Digest: "digest-1",
				Metadata: map[string]string{
					"language":         "sql",
					"artifact_type":    "schema",
					"template_dialect": "ansi",
					"iac_relevant":     "true",
					"commit_sha":       "abc123",
				},
			},
			{
				Path:    "old.sql",
				Deleted: true,
			},
		},
	})
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.RecordCount, 2; got != want {
		t.Fatalf("Write().RecordCount = %d, want %d", got, want)
	}
	if got, want := result.DeletedCount, 1; got != want {
		t.Fatalf("Write().DeletedCount = %d, want %d", got, want)
	}
	if got, want := len(db.execs), 3; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if !strings.Contains(db.execs[0].query, "INSERT INTO content_files") {
		t.Fatalf("upsert query = %q, want content_files insert", db.execs[0].query)
	}
	if strings.Contains(db.execs[0].query, "content_entities") {
		t.Fatalf("upsert query = %q, want no entity insert", db.execs[0].query)
	}

	args := db.execs[0].args
	if got, want := args[0], "repository:r_test"; got != want {
		t.Fatalf("repo_id arg = %v, want %v", got, want)
	}
	if got, want := args[1], "schema.sql"; got != want {
		t.Fatalf("relative_path arg = %v, want %v", got, want)
	}
	if got, want := args[2], "abc123"; got != want {
		t.Fatalf("commit_sha arg = %v, want %v", got, want)
	}
	if got, want := args[3], "CREATE TABLE users (\n  id BIGINT\n);\n"; got != want {
		t.Fatalf("content arg = %q, want %q", got, want)
	}
	if got, want := args[4], "digest-1"; got != want {
		t.Fatalf("content_hash arg = %v, want %v", got, want)
	}
	if got, want := args[5], 3; got != want {
		t.Fatalf("line_count arg = %v, want %v", got, want)
	}
	if got, want := args[6], "sql"; got != want {
		t.Fatalf("language arg = %v, want %v", got, want)
	}
	if got, want := args[7], "schema"; got != want {
		t.Fatalf("artifact_type arg = %v, want %v", got, want)
	}
	if got, want := args[8], "ansi"; got != want {
		t.Fatalf("template_dialect arg = %v, want %v", got, want)
	}
	if got, want := args[9], true; got != want {
		t.Fatalf("iac_relevant arg = %v, want %v", got, want)
	}
	if got, want := args[10], now; got != want {
		t.Fatalf("indexed_at arg = %v, want %v", got, want)
	}

	if !strings.Contains(db.execs[1].query, "DELETE FROM content_entities") {
		t.Fatalf("cleanup query = %q, want content_entities delete", db.execs[1].query)
	}
	if !strings.Contains(db.execs[2].query, "DELETE FROM content_files") {
		t.Fatalf("delete query = %q, want content_files delete", db.execs[2].query)
	}
	if got, want := db.execs[2].args[0], "repository:r_test"; got != want {
		t.Fatalf("delete repo_id arg = %v, want %v", got, want)
	}
	if got, want := db.execs[2].args[1], "old.sql"; got != want {
		t.Fatalf("delete relative_path arg = %v, want %v", got, want)
	}
}

func TestPostgresContentWriterRejectsMissingRepoID(t *testing.T) {
	t.Parallel()

	writer := pg.NewContentWriter(&recordingExecQueryer{})
	_, err := writer.Write(context.Background(), content.Materialization{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		Records: []content.Record{{
			Path: "schema.sql",
			Body: "SELECT 1;\n",
		}},
	})
	if err == nil {
		t.Fatal("Write() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "repo_id") {
		t.Fatalf("Write() error = %q, want repo_id context", err)
	}
}

type recordingExecQueryer struct {
	execs []recordingExecCall
}

type recordingExecCall struct {
	query string
	args  []any
}

func (f *recordingExecQueryer) ExecContext(
	_ context.Context,
	query string,
	args ...any,
) (sql.Result, error) {
	f.execs = append(f.execs, recordingExecCall{query: query, args: args})
	return recordingResult{}, nil
}

func (f *recordingExecQueryer) QueryContext(
	_ context.Context,
	_ string,
	_ ...any,
) (pg.Rows, error) {
	return nil, context.Canceled
}

type recordingResult struct{}

func (recordingResult) LastInsertId() (int64, error) { return 0, nil }

func (recordingResult) RowsAffected() (int64, error) { return 0, nil }
