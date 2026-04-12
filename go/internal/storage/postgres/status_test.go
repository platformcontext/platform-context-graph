package postgres

import (
	"context"
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
					{"active", int64(3)},
					{"failed", int64(1)},
				},
			},
			{
				rows: [][]any{
					{"active", int64(2)},
					{"completed", int64(4)},
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
					{"repository", int64(3), int64(1), int64(0), 90.0},
					{"shared-platform", int64(1), int64(0), int64(1), 30.0},
				},
			},
			{
				rows: [][]any{
					{int64(9), int64(4), int64(1), int64(2), int64(1), int64(3), int64(1), 90.0, int64(0)},
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
		Failed:               1,
		OldestOutstandingAge: 90 * time.Second,
		OverdueClaims:        0,
	}
	if got.Queue != wantQueue {
		t.Fatalf("ReadRawSnapshot().Queue = %#v, want %#v", got.Queue, wantQueue)
	}
	if len(got.ScopeCounts) != 2 {
		t.Fatalf("ReadRawSnapshot().ScopeCounts len = %d, want 2", len(got.ScopeCounts))
	}
	if len(got.StageCounts) != 3 {
		t.Fatalf("ReadRawSnapshot().StageCounts len = %d, want 3", len(got.StageCounts))
	}
	if len(got.DomainBacklogs) != 2 {
		t.Fatalf("ReadRawSnapshot().DomainBacklogs len = %d, want 2", len(got.DomainBacklogs))
	}
	if got.DomainBacklogs[0].OldestAge != 90*time.Second {
		t.Fatalf("ReadRawSnapshot().DomainBacklogs[0].OldestAge = %v, want %v", got.DomainBacklogs[0].OldestAge, 90*time.Second)
	}

	if len(queryer.queries) != 5 {
		t.Fatalf("QueryContext() call count = %d, want 5", len(queryer.queries))
	}
	for _, want := range []string{
		"FROM ingestion_scopes",
		"FROM scope_generations",
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
		default:
			return fmt.Errorf("unsupported scan target %T", dest[i])
		}
	}
	r.index++
	return nil
}

func (r *fakeRows) Err() error { return nil }

func (r *fakeRows) Close() error { return nil }
