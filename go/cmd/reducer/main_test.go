package main

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

// stubNeo4jExecutor is a no-op executor for tests that don't exercise Neo4j.
type stubNeo4jExecutor struct{}

func (stubNeo4jExecutor) Execute(_ context.Context, _ sourceneo4j.Statement) error { return nil }

// stubCypherExecutor is a no-op CypherExecutor for tests that don't exercise Neo4j.
type stubCypherExecutor struct{}

func (stubCypherExecutor) ExecuteCypher(_ context.Context, _ string, _ map[string]any) error {
	return nil
}

// stubCypherReader always reports no canonical nodes exist (safe no-op for tests).
type stubCypherReader struct{}

func (stubCypherReader) QueryCypherExists(_ context.Context, _ string, _ map[string]any) (bool, error) {
	return false, nil
}

func TestBuildReducerServiceWiresDefaultRuntimeAndQueue(t *testing.T) {
	t.Parallel()

	db := &fakeReducerDB{}
	service, err := buildReducerService(db, stubNeo4jExecutor{}, stubCypherExecutor{}, postgres.NewSharedIntentStore(db), stubCypherReader{}, func(string) string { return "" }, nil, nil, nil)
	if err != nil {
		t.Fatalf("buildReducerService() error = %v, want nil", err)
	}
	if service.PollInterval <= 0 {
		t.Fatalf("buildReducerService() poll interval = %v, want positive", service.PollInterval)
	}
	if service.WorkSource == nil {
		t.Fatal("buildReducerService() work source = nil, want non-nil")
	}
	if service.Executor == nil {
		t.Fatal("buildReducerService() executor = nil, want non-nil")
	}
	if service.WorkSink == nil {
		t.Fatal("buildReducerService() work sink = nil, want non-nil")
	}
}

func TestBuildReducerServiceWiresPostgresWorkloadIdentityWriter(t *testing.T) {
	t.Parallel()

	db := &fakeReducerDB{}
	service, err := buildReducerService(db, stubNeo4jExecutor{}, stubCypherExecutor{}, postgres.NewSharedIntentStore(db), stubCypherReader{}, func(string) string { return "" }, nil, nil, nil)
	if err != nil {
		t.Fatalf("buildReducerService() error = %v, want nil", err)
	}

	intent := reducer.Intent{
		IntentID:        "intent-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          reducer.DomainWorkloadIdentity,
		Cause:           "shared follow-up",
		EntityKeys:      []string{"repo-a"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          reducer.IntentStatusPending,
	}

	result, err := service.Executor.Execute(context.Background(), intent)
	if err != nil {
		t.Fatalf("Executor.Execute() error = %v, want nil", err)
	}
	if got, want := result.Status, reducer.ResultStatusSucceeded; got != want {
		t.Fatalf("Executor.Execute().Status = %q, want %q", got, want)
	}
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("ExecContext calls = %d, want %d", got, want)
	}
	if got := db.execs[0].query; !strings.Contains(got, "INSERT INTO fact_records") {
		t.Fatalf("ExecContext query = %q, want fact_records insert", got)
	}
}

func TestBuildReducerServiceWiresPostgresCloudAssetResolutionWriter(t *testing.T) {
	t.Parallel()

	db := &fakeReducerDB{}
	service, err := buildReducerService(db, stubNeo4jExecutor{}, stubCypherExecutor{}, postgres.NewSharedIntentStore(db), stubCypherReader{}, func(string) string { return "" }, nil, nil, nil)
	if err != nil {
		t.Fatalf("buildReducerService() error = %v, want nil", err)
	}

	intent := reducer.Intent{
		IntentID:        "intent-2",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          reducer.DomainCloudAssetResolution,
		Cause:           "shared follow-up",
		EntityKeys:      []string{"aws:s3:bucket:logs-prod"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          reducer.IntentStatusPending,
	}

	result, err := service.Executor.Execute(context.Background(), intent)
	if err != nil {
		t.Fatalf("Executor.Execute() error = %v, want nil", err)
	}
	if got, want := result.Status, reducer.ResultStatusSucceeded; got != want {
		t.Fatalf("Executor.Execute().Status = %q, want %q", got, want)
	}
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("ExecContext calls = %d, want %d", got, want)
	}
	if got := db.execs[0].query; !strings.Contains(got, "INSERT INTO fact_records") {
		t.Fatalf("ExecContext query = %q, want fact_records insert", got)
	}
}

func TestBuildReducerServiceWiresRetryConfigFromEnv(t *testing.T) {
	t.Parallel()

	db := &fakeReducerDB{}
	service, err := buildReducerService(db, stubNeo4jExecutor{}, stubCypherExecutor{}, postgres.NewSharedIntentStore(db), stubCypherReader{}, func(name string) string {
		switch name {
		case reducerRetryDelayEnv:
			return "2m"
		case reducerMaxAttemptsEnv:
			return "5"
		default:
			return ""
		}
	}, nil, nil, nil)
	if err != nil {
		t.Fatalf("buildReducerService() error = %v, want nil", err)
	}

	queue, ok := service.WorkSource.(postgres.ReducerQueue)
	if !ok {
		t.Fatalf("WorkSource type = %T, want postgres.ReducerQueue", service.WorkSource)
	}
	if got, want := queue.RetryDelay, 2*time.Minute; got != want {
		t.Fatalf("RetryDelay = %v, want %v", got, want)
	}
	if got, want := queue.MaxAttempts, 5; got != want {
		t.Fatalf("MaxAttempts = %d, want %d", got, want)
	}
}

type fakeReducerDB struct {
	execs []fakeReducerExecCall
}

type fakeReducerExecCall struct {
	query string
	args  []any
}

func (f *fakeReducerDB) ExecContext(
	_ context.Context,
	query string,
	args ...any,
) (sql.Result, error) {
	f.execs = append(f.execs, fakeReducerExecCall{query: query, args: args})
	return fakeReducerResult{}, nil
}

func (f *fakeReducerDB) QueryContext(_ context.Context, query string, args ...any) (postgres.Rows, error) {
	// Generation freshness check: return a row matching the intent's generation
	// so the guard treats the intent as current.
	if strings.Contains(query, "active_generation_id") && strings.Contains(query, "ingestion_scopes") {
		scopeGenID := ""
		if len(args) > 0 {
			// Look up what generation the intent carries — fake DB always reports
			// the intent's generation as active so execution proceeds.
			scopeGenID = "generation-456"
		}
		return &fakeGenerationRows{value: &scopeGenID, read: false}, nil
	}
	return nil, fmt.Errorf("unexpected query: %s", query)
}

// fakeGenerationRows returns a single active_generation_id row.
type fakeGenerationRows struct {
	value *string
	read  bool
}

func (r *fakeGenerationRows) Next() bool {
	if r.read {
		return false
	}
	r.read = true
	return true
}

func (r *fakeGenerationRows) Scan(dest ...any) error {
	if len(dest) != 1 {
		return fmt.Errorf("scan: got %d dest, want 1", len(dest))
	}
	switch d := dest[0].(type) {
	case *sql.NullString:
		*d = sql.NullString{String: *r.value, Valid: true}
	default:
		return fmt.Errorf("unsupported scan dest type %T", dest[0])
	}
	return nil
}

func (r *fakeGenerationRows) Err() error  { return nil }
func (r *fakeGenerationRows) Close() error { return nil }

type fakeReducerResult struct{}

func (fakeReducerResult) LastInsertId() (int64, error) { return 0, nil }
func (fakeReducerResult) RowsAffected() (int64, error) { return 1, nil }
