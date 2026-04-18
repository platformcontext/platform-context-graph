package query

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"fmt"
	"io"
	"strings"
	"sync/atomic"
	"testing"
)

func TestContentReaderSearchFileContentAnyRepo(t *testing.T) {
	t.Parallel()

	db, recorder := openRecordingContentReaderDB(t, []recordingContentReaderQueryResult{
		{
			columns: []string{
				"repo_id", "relative_path", "commit_sha", "content",
				"content_hash", "line_count", "language", "artifact_type",
			},
			rows: [][]driver.Value{
				{
					"helm-charts", "charts/api-node-boats/values-qa.yaml", "", "",
					"hash-1", int64(18), "yaml", "helm_values",
				},
			},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.SearchFileContentAnyRepo(context.Background(), "api-node-boats", 10)
	if err != nil {
		t.Fatalf("SearchFileContentAnyRepo() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}
	if got, want := results[0].RepoID, "helm-charts"; got != want {
		t.Fatalf("results[0].RepoID = %#v, want %#v", got, want)
	}

	if len(recorder.args) != 1 {
		t.Fatalf("len(recorder.args) = %d, want 1", len(recorder.args))
	}
	if got, want := len(recorder.args[0]), 2; got != want {
		t.Fatalf("len(query args) = %d, want %d", got, want)
	}
	if got, want := recorder.args[0][0], "api-node-boats"; got != want {
		t.Fatalf("query arg pattern = %#v, want %#v", got, want)
	}
	if got, want := numericDriverValue(t, recorder.args[0][1]), int64(10); got != want {
		t.Fatalf("query arg limit = %d, want %d", got, want)
	}
	if strings.Contains(recorder.queries[0], "repo_id =") {
		t.Fatalf("query = %q, want cross-repo query without repo filter", recorder.queries[0])
	}
}

func TestContentReaderSearchFileContentAnyRepoDefaultsLimit(t *testing.T) {
	t.Parallel()

	db, recorder := openRecordingContentReaderDB(t, []recordingContentReaderQueryResult{
		{
			columns: []string{
				"repo_id", "relative_path", "commit_sha", "content",
				"content_hash", "line_count", "language", "artifact_type",
			},
			rows: [][]driver.Value{},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.SearchFileContentAnyRepo(context.Background(), "qa.example.internal", 0)
	if err != nil {
		t.Fatalf("SearchFileContentAnyRepo() error = %v, want nil", err)
	}
	if len(results) != 0 {
		t.Fatalf("len(results) = %d, want 0", len(results))
	}

	if len(recorder.args) != 1 {
		t.Fatalf("len(recorder.args) = %d, want 1", len(recorder.args))
	}
	if got, want := numericDriverValue(t, recorder.args[0][1]), int64(50); got != want {
		t.Fatalf("query arg default limit = %d, want %d", got, want)
	}
}

type recordingContentReaderQueryResult struct {
	columns []string
	rows    [][]driver.Value
	err     error
}

type recordingContentReader struct {
	queries []string
	args    [][]driver.Value
}

func openRecordingContentReaderDB(t *testing.T, results []recordingContentReaderQueryResult) (*sql.DB, *recordingContentReader) {
	t.Helper()

	name := fmt.Sprintf("content-reader-recording-test-%d", atomic.AddUint64(&recordingContentReaderDriverSeq, 1))
	recorder := &recordingContentReader{}
	sql.Register(name, &recordingContentReaderDriver{
		results:  results,
		recorder: recorder,
	})

	db, err := sql.Open(name, "")
	if err != nil {
		t.Fatalf("sql.Open() error = %v, want nil", err)
	}
	t.Cleanup(func() {
		_ = db.Close()
	})
	return db, recorder
}

var recordingContentReaderDriverSeq uint64

type recordingContentReaderDriver struct {
	results  []recordingContentReaderQueryResult
	recorder *recordingContentReader
}

func (d *recordingContentReaderDriver) Open(string) (driver.Conn, error) {
	return &recordingContentReaderConn{
		results:  append([]recordingContentReaderQueryResult(nil), d.results...),
		recorder: d.recorder,
	}, nil
}

type recordingContentReaderConn struct {
	results  []recordingContentReaderQueryResult
	recorder *recordingContentReader
}

func (c *recordingContentReaderConn) Prepare(string) (driver.Stmt, error) {
	return nil, fmt.Errorf("Prepare not implemented")
}

func (c *recordingContentReaderConn) Close() error {
	return nil
}

func (c *recordingContentReaderConn) Begin() (driver.Tx, error) {
	return nil, fmt.Errorf("Begin not implemented")
}

func (c *recordingContentReaderConn) QueryContext(_ context.Context, query string, args []driver.NamedValue) (driver.Rows, error) {
	c.recorder.queries = append(c.recorder.queries, query)

	recordedArgs := make([]driver.Value, 0, len(args))
	for _, arg := range args {
		recordedArgs = append(recordedArgs, arg.Value)
	}
	c.recorder.args = append(c.recorder.args, recordedArgs)

	if len(c.results) == 0 {
		return nil, fmt.Errorf("unexpected query")
	}
	result := c.results[0]
	c.results = c.results[1:]
	if result.err != nil {
		return nil, result.err
	}
	return &recordingContentReaderRows{columns: result.columns, rows: result.rows}, nil
}

type recordingContentReaderRows struct {
	columns []string
	rows    [][]driver.Value
	index   int
}

func (r *recordingContentReaderRows) Columns() []string {
	return r.columns
}

func (r *recordingContentReaderRows) Close() error {
	return nil
}

func (r *recordingContentReaderRows) Next(dest []driver.Value) error {
	if r.index >= len(r.rows) {
		return io.EOF
	}
	copy(dest, r.rows[r.index])
	r.index++
	return nil
}

func numericDriverValue(t *testing.T, value driver.Value) int64 {
	t.Helper()

	switch typed := value.(type) {
	case int64:
		return typed
	case int:
		return int64(typed)
	default:
		t.Fatalf("driver value type = %T, want numeric", value)
		return 0
	}
}
