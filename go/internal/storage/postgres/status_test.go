package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

func TestStatusStoreReadRawSnapshot(t *testing.T) {
	t.Parallel()

	queryer := &fakeQueryer{
		responses: []fakeRows{
			{
				rows: [][]any{
					{"active", int64(5)},
					{"pending", int64(1)},
					{"completed", int64(4)},
					{"superseded", int64(3)},
					{"failed", int64(1)},
					{"inactive", int64(2)},
				},
			},
			{
				rows: [][]any{
					{"active", int64(5)},
					{"pending", int64(2)},
					{"completed", int64(4)},
					{"superseded", int64(3)},
					{"failed", int64(1)},
					{"inactive", int64(2)},
				},
			},
			{
				rows: [][]any{
					{"scope-1", "generation-b", "active", "snapshot", "fresh snapshot", time.Date(2026, 4, 12, 15, 45, 0, 0, time.UTC), time.Date(2026, 4, 12, 15, 46, 0, 0, time.UTC), nil, "generation-b"},
					{"scope-1", "generation-a", "superseded", "snapshot", "changed files", time.Date(2026, 4, 12, 15, 30, 0, 0, time.UTC), time.Date(2026, 4, 12, 15, 31, 0, 0, time.UTC), time.Date(2026, 4, 12, 15, 40, 0, 0, time.UTC), "generation-b"},
				},
			},
			{
				rows: [][]any{
					{"projector", "pending", int64(2)},
					{"projector", "running", int64(1)},
					{"reducer", "retrying", int64(1)},
				},
			},
			{
				rows: [][]any{
					{"repository", int64(3), int64(1), int64(0), int64(0), 90.0},
					{"shared-platform", int64(1), int64(0), int64(1), int64(0), 30.0},
				},
			},
			{
				rows: [][]any{
					{int64(9), int64(4), int64(1), int64(2), int64(1), int64(3), int64(1), int64(0), 90.0, int64(0)},
				},
			},
		},
	}

	store := NewStatusStore(queryer)
	got, err := store.ReadRawSnapshot(context.Background(), time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("ReadRawSnapshot() error = %v, want nil", err)
	}

	wantQueue := statuspkg.QueueSnapshot{
		Total:                9,
		Outstanding:          4,
		Pending:              1,
		InFlight:             2,
		Retrying:             1,
		Succeeded:            3,
		Failed:               0,
		DeadLetter:           1,
		OldestOutstandingAge: 90 * time.Second,
		OverdueClaims:        0,
	}
	if got.Queue != wantQueue {
		t.Fatalf("ReadRawSnapshot().Queue = %#v, want %#v", got.Queue, wantQueue)
	}
	if len(got.ScopeCounts) != 6 {
		t.Fatalf("ReadRawSnapshot().ScopeCounts len = %d, want 6", len(got.ScopeCounts))
	}
	if got.ScopeActivity.Active != 5 {
		t.Fatalf("ReadRawSnapshot().ScopeActivity.Active = %d, want 5", got.ScopeActivity.Active)
	}
	if got.ScopeActivity.Changed != 2 {
		t.Fatalf("ReadRawSnapshot().ScopeActivity.Changed = %d, want 2", got.ScopeActivity.Changed)
	}
	if got.ScopeActivity.Unchanged != 3 {
		t.Fatalf("ReadRawSnapshot().ScopeActivity.Unchanged = %d, want 3", got.ScopeActivity.Unchanged)
	}
	if got.GenerationHistory.Active != 5 {
		t.Fatalf("ReadRawSnapshot().GenerationHistory.Active = %d, want 5", got.GenerationHistory.Active)
	}
	if got.GenerationHistory.Pending != 2 {
		t.Fatalf("ReadRawSnapshot().GenerationHistory.Pending = %d, want 2", got.GenerationHistory.Pending)
	}
	if got.GenerationHistory.Completed != 4 {
		t.Fatalf("ReadRawSnapshot().GenerationHistory.Completed = %d, want 4", got.GenerationHistory.Completed)
	}
	if got.GenerationHistory.Superseded != 3 {
		t.Fatalf("ReadRawSnapshot().GenerationHistory.Superseded = %d, want 3", got.GenerationHistory.Superseded)
	}
	if got.GenerationHistory.Failed != 1 {
		t.Fatalf("ReadRawSnapshot().GenerationHistory.Failed = %d, want 1", got.GenerationHistory.Failed)
	}
	if got.GenerationHistory.Other != 2 {
		t.Fatalf("ReadRawSnapshot().GenerationHistory.Other = %d, want 2", got.GenerationHistory.Other)
	}
	if len(got.StageCounts) != 3 {
		t.Fatalf("ReadRawSnapshot().StageCounts len = %d, want 3", len(got.StageCounts))
	}
	if len(got.GenerationTransitions) != 2 {
		t.Fatalf("ReadRawSnapshot().GenerationTransitions len = %d, want 2", len(got.GenerationTransitions))
	}
	if got.GenerationTransitions[0].CurrentActiveGenerationID != "generation-b" {
		t.Fatalf("ReadRawSnapshot().GenerationTransitions[0].CurrentActiveGenerationID = %q, want %q", got.GenerationTransitions[0].CurrentActiveGenerationID, "generation-b")
	}
	if len(got.DomainBacklogs) != 2 {
		t.Fatalf("ReadRawSnapshot().DomainBacklogs len = %d, want 2", len(got.DomainBacklogs))
	}
	if got.DomainBacklogs[0].OldestAge != 90*time.Second {
		t.Fatalf("ReadRawSnapshot().DomainBacklogs[0].OldestAge = %v, want %v", got.DomainBacklogs[0].OldestAge, 90*time.Second)
	}

	if len(queryer.queries) != 6 {
		t.Fatalf("QueryContext() call count = %d, want 6", len(queryer.queries))
	}
	for _, want := range []string{
		"FROM ingestion_scopes",
		"FROM scope_generations",
		"JOIN ingestion_scopes",
		"activated_at",
		"superseded_at",
		"FROM fact_work_items",
	} {
		joined := strings.Join(queryer.queries, "\n")
		if !strings.Contains(joined, want) {
			t.Fatalf("queries missing %q:\n%s", want, joined)
		}
	}
}

func TestStatusStoreReadRawSnapshotPropagatesQueryErrors(t *testing.T) {
	t.Parallel()

	queryer := &fakeQueryer{
		responses: []fakeRows{
			{err: errors.New("boom")},
		},
	}

	store := NewStatusStore(queryer)
	_, err := store.ReadRawSnapshot(context.Background(), time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC))
	if err == nil {
		t.Fatal("ReadRawSnapshot() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "list scope counts") {
		t.Fatalf("ReadRawSnapshot() error = %q, want prefix context", err)
	}
}

func TestStatusQueriesUseAggregateFilterSyntax(t *testing.T) {
	t.Parallel()

	for name, query := range map[string]string{
		"domainBacklogQuery": domainBacklogQuery,
		"queueSnapshotQuery": queueSnapshotQuery,
	} {
		if !strings.Contains(query, "MIN(created_at)\n                 FILTER") {
			t.Fatalf("%s missing aggregate FILTER placement:\n%s", name, query)
		}
		if strings.Contains(query, "EXTRACT(EPOCH FROM ($1 - MIN(created_at)))\n           FILTER") {
			t.Fatalf("%s uses invalid FILTER placement:\n%s", name, query)
		}
	}
}

type fakeQueryer struct {
	responses []fakeRows
	queries   []string
}

func (q *fakeQueryer) QueryContext(_ context.Context, query string, _ ...any) (Rows, error) {
	q.queries = append(q.queries, query)
	if len(q.responses) == 0 {
		return nil, fmt.Errorf("unexpected query: %s", query)
	}

	rows := q.responses[0]
	q.responses = q.responses[1:]
	if rows.err != nil {
		return nil, rows.err
	}
	return &rows, nil
}

type fakeRows struct {
	rows  [][]any
	err   error
	index int
}

func (r *fakeRows) Next() bool {
	return r.index < len(r.rows)
}

func (r *fakeRows) Scan(dest ...any) error {
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
		case *int64:
			value, ok := row[i].(int64)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want int64", i, row[i])
			}
			*target = value
		case *float64:
			value, ok := row[i].(float64)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want float64", i, row[i])
			}
			*target = value
		case *time.Time:
			value, ok := row[i].(time.Time)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want time.Time", i, row[i])
			}
			*target = value
		case *sql.NullTime:
			switch value := row[i].(type) {
			case nil:
				*target = sql.NullTime{}
			case time.Time:
				*target = sql.NullTime{Time: value, Valid: true}
			default:
				return fmt.Errorf("row[%d] type = %T, want time.Time or nil", i, row[i])
			}
		default:
			return fmt.Errorf("unsupported scan target %T", dest[i])
		}
	}
	r.index++
	return nil
}

func (r *fakeRows) Err() error { return nil }

func (r *fakeRows) Close() error { return nil }
