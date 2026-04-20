package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestProjectorQueueClaimReturnsScopeGenerationWork(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{
				rows: [][]any{{
					"scope-123",
					"git",
					"repository",
					"",
					"git",
					"repo-123",
					"generation-456",
					1,
					time.Date(2026, time.April, 12, 10, 0, 0, 0, time.UTC),
					time.Date(2026, time.April, 12, 10, 5, 0, 0, time.UTC),
					"pending",
					"snapshot",
					"",
					[]byte(`{"repo_id":"repository:r_test"}`),
				}},
			},
		},
	}

	queue := ProjectorQueue{
		db:            db,
		LeaseOwner:    "projector-1",
		LeaseDuration: 30 * time.Second,
		Now:           func() time.Time { return now },
	}

	work, ok, err := queue.Claim(context.Background())
	if err != nil {
		t.Fatalf("Claim() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Claim() ok = false, want true")
	}
	if got, want := work.Scope.ScopeID, "scope-123"; got != want {
		t.Fatalf("Claim().Scope.ScopeID = %q, want %q", got, want)
	}
	if got, want := work.Generation.GenerationID, "generation-456"; got != want {
		t.Fatalf("Claim().Generation.GenerationID = %q, want %q", got, want)
	}
	if got, want := work.AttemptCount, 1; got != want {
		t.Fatalf("Claim().AttemptCount = %d, want %d", got, want)
	}
	if !strings.Contains(db.queries[0].query, "stage = 'projector'") {
		t.Fatalf("claim query = %q, want projector stage filter", db.queries[0].query)
	}
}

func TestProjectorQueueClaimPopulatesScopeMetadataFromPayload(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{
				rows: [][]any{{
					"scope-123",
					"git",
					"repository",
					"",
					"git",
					"repo-123",
					"generation-456",
					2,
					time.Date(2026, time.April, 12, 10, 0, 0, 0, time.UTC),
					time.Date(2026, time.April, 12, 10, 5, 0, 0, time.UTC),
					"pending",
					"snapshot",
					"",
					[]byte(`{"repo_id":"repository:r_test","source_key":"repo-123"}`),
				}},
			},
		},
	}

	queue := ProjectorQueue{
		db:            db,
		LeaseOwner:    "projector-1",
		LeaseDuration: 30 * time.Second,
		Now:           func() time.Time { return now },
	}

	work, ok, err := queue.Claim(context.Background())
	if err != nil {
		t.Fatalf("Claim() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Claim() ok = false, want true")
	}
	if got, want := work.Scope.Metadata["repo_id"], "repository:r_test"; got != want {
		t.Fatalf("Claim().Scope.Metadata[repo_id] = %q, want %q", got, want)
	}
}

func TestProjectorQueueEnqueueInsertsProjectorStageWork(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{}
	queue := ProjectorQueue{
		db:  db,
		Now: func() time.Time { return now },
	}

	err := queue.Enqueue(
		context.Background(),
		"scope-123",
		"generation-456",
	)
	if err != nil {
		t.Fatalf("Enqueue() error = %v, want nil", err)
	}
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if !strings.Contains(db.execs[0].query, "INSERT INTO fact_work_items") {
		t.Fatalf("enqueue query = %q, want fact_work_items insert", db.execs[0].query)
	}
	if got, want := db.execs[0].args[3], "source_local"; got != want {
		t.Fatalf("domain arg = %v, want %v", got, want)
	}
}

func TestReducerQueueEnqueueAndClaimRoundTrip(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{
				rows: [][]any{{
					"reducer_scope-123_generation-456_workload_identity_repo-123_fact-1_20260412110000.000000000_0",
					"scope-123",
					"generation-456",
					"workload_identity",
					1,
					now,
					now,
					[]byte(`{"entity_key":"repo-123","reason":"shared follow-up","fact_id":"fact-1","source_system":"git"}`),
				}},
			},
		},
	}

	queue := ReducerQueue{
		db:            db,
		LeaseOwner:    "reducer-1",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return now },
	}

	result, err := queue.Enqueue(context.Background(), []projector.ReducerIntent{{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		Domain:       "workload_identity",
		EntityKey:    "repo-123",
		Reason:       "shared follow-up",
		FactID:       "fact-1",
		SourceSystem: "git",
	}})
	if err != nil {
		t.Fatalf("Enqueue() error = %v, want nil", err)
	}
	if got, want := result.Count, 1; got != want {
		t.Fatalf("Enqueue().Count = %d, want %d", got, want)
	}

	intent, ok, err := queue.Claim(context.Background())
	if err != nil {
		t.Fatalf("Claim() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Claim() ok = false, want true")
	}
	if got, want := intent.Domain, reducer.DomainWorkloadIdentity; got != want {
		t.Fatalf("Claim().Domain = %q, want %q", got, want)
	}
	if got, want := intent.SourceSystem, "git"; got != want {
		t.Fatalf("Claim().SourceSystem = %q, want %q", got, want)
	}
	if got, want := intent.EntityKeys[0], "repo-123"; got != want {
		t.Fatalf("Claim().EntityKeys[0] = %q, want %q", got, want)
	}
	if got, want := intent.AttemptCount, 1; got != want {
		t.Fatalf("Claim().AttemptCount = %d, want %d", got, want)
	}
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if !strings.Contains(db.execs[0].query, "INSERT INTO fact_work_items") {
		t.Fatalf("enqueue query = %q, want fact_work_items insert", db.execs[0].query)
	}
}

func TestReducerQueueEnqueueRejectsUnknownDomain(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	queue := ReducerQueue{
		db:            &fakeExecQueryer{},
		LeaseOwner:    "reducer-1",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return now },
	}

	_, err := queue.Enqueue(context.Background(), []projector.ReducerIntent{{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		Domain:       "not_a_real_domain",
		EntityKey:    "repo-123",
		Reason:       "shared follow-up",
		FactID:       "fact-1",
		SourceSystem: "git",
	}})
	if err == nil {
		t.Fatal("Enqueue() error = nil, want non-nil")
	}
}

func TestScanReducerIntentRejectsUnknownDomain(t *testing.T) {
	t.Parallel()

	rows := &queueFakeRows{
		rows: [][]any{{
			"intent-1",
			"scope-123",
			"generation-456",
			"not_a_real_domain",
			1,
			time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
			time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
			[]byte(`{"entity_key":"repo-123","reason":"shared follow-up","fact_id":"fact-1","source_system":"git"}`),
		}},
	}

	if _, err := scanReducerIntent(rows); err == nil {
		t.Fatal("scanReducerIntent() error = nil, want non-nil")
	}
}

func TestReducerQueueFailRetriesRetryableErrorWithinAttemptBudget(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{}
	queue := ReducerQueue{
		db:            db,
		LeaseOwner:    "reducer-1",
		LeaseDuration: time.Minute,
		RetryDelay:    2 * time.Minute,
		MaxAttempts:   3,
		Now:           func() time.Time { return now },
	}

	intent := reducer.Intent{
		IntentID:     "intent-1",
		AttemptCount: 1,
	}

	if err := queue.Fail(context.Background(), intent, retryableReducerTestError{message: "transient failure"}); err != nil {
		t.Fatalf("Fail() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE fact_work_items",
		"status = 'retrying'",
		"next_attempt_at = $5",
		"visible_at = $5",
		"failure_class = $2",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("retry query missing %q:\n%s", want, query)
		}
	}
	if got, want := db.execs[0].args[1], "reducer_retryable"; got != want {
		t.Fatalf("failure class = %v, want %v", got, want)
	}
	if got, want := db.execs[0].args[4], now.Add(2*time.Minute); got != want {
		t.Fatalf("next attempt = %v, want %v", got, want)
	}
}

func TestReducerQueueFailMarksRetryableErrorTerminalWhenAttemptBudgetExhausted(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{}
	queue := ReducerQueue{
		db:            db,
		LeaseOwner:    "reducer-1",
		LeaseDuration: time.Minute,
		RetryDelay:    2 * time.Minute,
		MaxAttempts:   2,
		Now:           func() time.Time { return now },
	}

	intent := reducer.Intent{
		IntentID:     "intent-1",
		AttemptCount: 2,
	}

	if err := queue.Fail(context.Background(), intent, retryableReducerTestError{message: "still broken"}); err != nil {
		t.Fatalf("Fail() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}

	query := db.execs[0].query
	for _, want := range []string{
		"UPDATE fact_work_items",
		"status = 'dead_letter'",
		"failure_class = $2",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("terminal query missing %q:\n%s", want, query)
		}
	}
	if got, want := db.execs[0].args[1], "reducer_failed"; got != want {
		t.Fatalf("failure class = %v, want %v", got, want)
	}
}

func TestReducerQueueAckAndFailUpdateClaimedWork(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC)
	db := &fakeExecQueryer{}
	queue := ReducerQueue{
		db:            db,
		LeaseOwner:    "reducer-1",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return now },
	}

	intent := reducer.Intent{IntentID: "intent-1"}
	if err := queue.Ack(context.Background(), intent, reducer.Result{}); err != nil {
		t.Fatalf("Ack() error = %v, want nil", err)
	}
	if err := queue.Fail(context.Background(), intent, errors.New("boom")); err != nil {
		t.Fatalf("Fail() error = %v, want nil", err)
	}
	if got, want := len(db.execs), 2; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
}

func TestBootstrapWorkItemSchemaIncludesPayloadAndLeaseOwner(t *testing.T) {
	t.Parallel()

	var workItemSQL string
	for _, def := range BootstrapDefinitions() {
		if def.Name == "fact_work_items" {
			workItemSQL = def.SQL
			break
		}
	}
	if workItemSQL == "" {
		t.Fatal("fact_work_items definition missing")
	}
	for _, want := range []string{"lease_owner TEXT NULL", "payload JSONB NOT NULL DEFAULT '{}'::jsonb"} {
		if !strings.Contains(workItemSQL, want) {
			t.Fatalf("work item SQL missing %q", want)
		}
	}
}

type fakeExecQueryer struct {
	execs          []fakeExecCall
	execErrors     []error
	execResults    []sql.Result
	queries        []fakeQueryCall
	queryResponses []queueFakeRows
}

type fakeExecCall struct {
	query string
	args  []any
}

type fakeQueryCall struct {
	query string
	args  []any
}

func (f *fakeExecQueryer) ExecContext(
	_ context.Context,
	query string,
	args ...any,
) (sql.Result, error) {
	f.execs = append(f.execs, fakeExecCall{query: query, args: args})
	if len(f.execErrors) > 0 {
		err := f.execErrors[0]
		f.execErrors = f.execErrors[1:]
		return nil, err
	}
	if len(f.execResults) > 0 {
		result := f.execResults[0]
		f.execResults = f.execResults[1:]
		return result, nil
	}
	return fakeResult{}, nil
}

func (f *fakeExecQueryer) QueryContext(
	_ context.Context,
	query string,
	args ...any,
) (Rows, error) {
	f.queries = append(f.queries, fakeQueryCall{query: query, args: args})
	if len(f.queryResponses) == 0 {
		return nil, fmt.Errorf("unexpected query: %s", query)
	}

	rows := f.queryResponses[0]
	f.queryResponses = f.queryResponses[1:]
	if rows.err != nil {
		return nil, rows.err
	}

	return &rows, nil
}

type queueFakeRows struct {
	rows  [][]any
	err   error
	index int
}

func (r *queueFakeRows) Next() bool {
	return r.index < len(r.rows)
}

func (r *queueFakeRows) Scan(dest ...any) error {
	if r.index >= len(r.rows) {
		return errors.New("scan called without row")
	}
	row := r.rows[r.index]
	if len(dest) != len(row) {
		return fmt.Errorf("scan destination count = %d, want %d", len(dest), len(row))
	}

	for i := range dest {
		switch target := dest[i].(type) {
		case *string:
			value, ok := row[i].(string)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want string", i, row[i])
			}
			*target = value
		case *bool:
			value, ok := row[i].(bool)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want bool", i, row[i])
			}
			*target = value
		case *[]byte:
			value, ok := row[i].([]byte)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want []byte", i, row[i])
			}
			*target = value
		case *time.Time:
			value, ok := row[i].(time.Time)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want time.Time", i, row[i])
			}
			*target = value
		case *int:
			value, ok := row[i].(int)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want int", i, row[i])
			}
			*target = value
		case *sql.NullString:
			value, ok := row[i].(sql.NullString)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want sql.NullString", i, row[i])
			}
			*target = value
		case *sql.NullBool:
			value, ok := row[i].(sql.NullBool)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want sql.NullBool", i, row[i])
			}
			*target = value
		case *sql.NullInt64:
			value, ok := row[i].(sql.NullInt64)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want sql.NullInt64", i, row[i])
			}
			*target = value
		default:
			return fmt.Errorf("unsupported scan target %T", dest[i])
		}
	}

	r.index++
	return nil
}

func (r *queueFakeRows) Err() error { return nil }

func (r *queueFakeRows) Close() error { return nil }

type fakeResult struct{}

func (fakeResult) LastInsertId() (int64, error) { return 0, nil }

func (fakeResult) RowsAffected() (int64, error) { return 1, nil }

type retryableReducerTestError struct {
	message string
}

func (e retryableReducerTestError) Error() string {
	return e.message
}

func (e retryableReducerTestError) Retryable() bool {
	return true
}
