package main

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildReducerServiceWiresDefaultRuntimeAndQueue(t *testing.T) {
	t.Parallel()

	db := &fakeReducerDB{}
	service, err := buildReducerService(db, func(string) string { return "" })
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
	service, err := buildReducerService(db, func(string) string { return "" })
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
	service, err := buildReducerService(db, func(string) string { return "" })
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
	service, err := buildReducerService(db, func(name string) string {
		switch name {
		case reducerRetryDelayEnv:
			return "2m"
		case reducerMaxAttemptsEnv:
			return "5"
		default:
			return ""
		}
	})
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

func (f *fakeReducerDB) QueryContext(_ context.Context, query string, _ ...any) (postgres.Rows, error) {
	return nil, fmt.Errorf("unexpected query: %s", query)
}

type fakeReducerResult struct{}

func (fakeReducerResult) LastInsertId() (int64, error) { return 0, nil }
func (fakeReducerResult) RowsAffected() (int64, error) { return 1, nil }
