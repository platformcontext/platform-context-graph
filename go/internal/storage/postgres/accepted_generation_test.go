package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"testing"
)

func TestAcceptedGenerationLookup(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name           string
		repositoryID   string
		sourceRunID    string
		setupRows      []acceptedGenRow
		wantGeneration string
		wantFound      bool
	}{
		{
			name:         "returns generation when row exists",
			repositoryID: "repository:r_api",
			sourceRunID:  "run-001",
			setupRows: []acceptedGenRow{
				{
					repositoryID:          "repository:r_api",
					sourceRunID:           "run-001",
					acceptedGenerationID:  "gen-abc-123",
					sharedProjectionPending: true,
				},
			},
			wantGeneration: "gen-abc-123",
			wantFound:      true,
		},
		{
			name:         "returns not found when no matching row exists",
			repositoryID: "repository:r_payments",
			sourceRunID:  "run-002",
			setupRows: []acceptedGenRow{
				{
					repositoryID:          "repository:r_api",
					sourceRunID:           "run-001",
					acceptedGenerationID:  "gen-abc-123",
					sharedProjectionPending: true,
				},
			},
			wantGeneration: "",
			wantFound:      false,
		},
		{
			name:         "returns not found when no rows at all",
			repositoryID: "repository:r_empty",
			sourceRunID:  "run-empty",
			setupRows:    nil,
			wantGeneration: "",
			wantFound:      false,
		},
		{
			name:         "returns most recent when multiple rows match",
			repositoryID: "repository:r_multi",
			sourceRunID:  "run-multi",
			setupRows: []acceptedGenRow{
				{
					repositoryID:          "repository:r_multi",
					sourceRunID:           "run-multi",
					acceptedGenerationID:  "gen-old",
					sharedProjectionPending: true,
				},
				{
					repositoryID:          "repository:r_multi",
					sourceRunID:           "run-multi",
					acceptedGenerationID:  "gen-new",
					sharedProjectionPending: true,
				},
			},
			wantGeneration: "gen-new",
			wantFound:      true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			db := newAcceptedGenerationTestDB(tt.setupRows)
			lookup := NewAcceptedGenerationLookup(db)

			gotGeneration, gotFound := lookup(tt.repositoryID, tt.sourceRunID)

			if gotGeneration != tt.wantGeneration {
				t.Errorf("generation = %q, want %q", gotGeneration, tt.wantGeneration)
			}
			if gotFound != tt.wantFound {
				t.Errorf("found = %v, want %v", gotFound, tt.wantFound)
			}
		})
	}
}

func TestAcceptedGenerationLookupQueryVerification(t *testing.T) {
	t.Parallel()

	db := &queryCapturingDB{
		rows: []acceptedGenRow{
			{
				repositoryID:          "repository:r_test",
				sourceRunID:           "run-test",
				acceptedGenerationID:  "gen-test",
				sharedProjectionPending: true,
			},
		},
	}

	lookup := NewAcceptedGenerationLookup(db)
	_, _ = lookup("repository:r_test", "run-test")

	if db.lastQuery == "" {
		t.Fatal("no query was executed")
	}

	// Verify the query structure
	if !strings.Contains(db.lastQuery, "SELECT accepted_generation_id") {
		t.Error("query should SELECT accepted_generation_id")
	}
	if !strings.Contains(db.lastQuery, "FROM fact_work_items") {
		t.Error("query should be FROM fact_work_items")
	}
	if !strings.Contains(db.lastQuery, "WHERE repository_id = $1") {
		t.Error("query should filter by repository_id = $1")
	}
	if !strings.Contains(db.lastQuery, "AND source_run_id = $2") {
		t.Error("query should filter by source_run_id = $2")
	}
	if !strings.Contains(db.lastQuery, "AND shared_projection_pending = TRUE") {
		t.Error("query should filter by shared_projection_pending = TRUE")
	}
	if !strings.Contains(db.lastQuery, "AND accepted_generation_id IS NOT NULL") {
		t.Error("query should filter by accepted_generation_id IS NOT NULL")
	}
	if !strings.Contains(db.lastQuery, "ORDER BY updated_at DESC") {
		t.Error("query should ORDER BY updated_at DESC")
	}
	if !strings.Contains(db.lastQuery, "LIMIT 1") {
		t.Error("query should LIMIT 1")
	}

	// Verify the parameters
	if len(db.lastArgs) != 2 {
		t.Fatalf("expected 2 query args, got %d", len(db.lastArgs))
	}
	if db.lastArgs[0] != "repository:r_test" {
		t.Errorf("arg[0] = %v, want repository:r_test", db.lastArgs[0])
	}
	if db.lastArgs[1] != "run-test" {
		t.Errorf("arg[1] = %v, want run-test", db.lastArgs[1])
	}
}

// -- test helpers --

type acceptedGenRow struct {
	repositoryID          string
	sourceRunID           string
	acceptedGenerationID  string
	sharedProjectionPending bool
}

// acceptedGenerationTestDB is an in-memory mock of ExecQueryer for testing
// accepted generation lookups.
type acceptedGenerationTestDB struct {
	rows []acceptedGenRow
}

func newAcceptedGenerationTestDB(rows []acceptedGenRow) *acceptedGenerationTestDB {
	return &acceptedGenerationTestDB{rows: rows}
}

func (db *acceptedGenerationTestDB) ExecContext(_ context.Context, _ string, _ ...any) (sql.Result, error) {
	return nil, fmt.Errorf("ExecContext not implemented in test stub")
}

func (db *acceptedGenerationTestDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	if !strings.Contains(query, "SELECT accepted_generation_id") {
		return nil, fmt.Errorf("unexpected query: %s", query)
	}

	if len(args) != 2 {
		return nil, fmt.Errorf("expected 2 args, got %d", len(args))
	}

	repositoryID := args[0].(string)
	sourceRunID := args[1].(string)

	var matchingRows [][]any
	for _, row := range db.rows {
		if row.repositoryID == repositoryID && row.sourceRunID == sourceRunID && row.sharedProjectionPending {
			matchingRows = append(matchingRows, []any{row.acceptedGenerationID})
		}
	}

	// Return the most recent (last in slice simulates ORDER BY updated_at DESC)
	if len(matchingRows) > 0 {
		return &acceptedGenTestRows{
			data: [][]any{matchingRows[len(matchingRows)-1]},
			idx:  -1,
		}, nil
	}

	return &acceptedGenTestRows{data: nil, idx: -1}, nil
}

// queryCapturingDB captures the last query and args for verification.
type queryCapturingDB struct {
	rows      []acceptedGenRow
	lastQuery string
	lastArgs  []any
}

func (db *queryCapturingDB) ExecContext(_ context.Context, _ string, _ ...any) (sql.Result, error) {
	return nil, fmt.Errorf("ExecContext not implemented in test stub")
}

func (db *queryCapturingDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	db.lastQuery = query
	db.lastArgs = args

	if len(args) != 2 {
		return nil, fmt.Errorf("expected 2 args, got %d", len(args))
	}

	repositoryID := args[0].(string)
	sourceRunID := args[1].(string)

	var matchingRows [][]any
	for _, row := range db.rows {
		if row.repositoryID == repositoryID && row.sourceRunID == sourceRunID && row.sharedProjectionPending {
			matchingRows = append(matchingRows, []any{row.acceptedGenerationID})
		}
	}

	if len(matchingRows) > 0 {
		return &acceptedGenTestRows{
			data: [][]any{matchingRows[len(matchingRows)-1]},
			idx:  -1,
		}, nil
	}

	return &acceptedGenTestRows{data: nil, idx: -1}, nil
}

// acceptedGenTestRows implements the Rows interface for testing.
type acceptedGenTestRows struct {
	data [][]any
	idx  int
}

func (r *acceptedGenTestRows) Next() bool {
	r.idx++
	return r.idx < len(r.data)
}

func (r *acceptedGenTestRows) Scan(dest ...any) error {
	if r.idx < 0 || r.idx >= len(r.data) {
		return sql.ErrNoRows
	}
	row := r.data[r.idx]
	if len(dest) != len(row) {
		return fmt.Errorf("scan: got %d dest, have %d cols", len(dest), len(row))
	}
	for i, val := range row {
		switch d := dest[i].(type) {
		case *string:
			*d = val.(string)
		default:
			return fmt.Errorf("unsupported scan dest type %T", dest[i])
		}
	}
	return nil
}

func (r *acceptedGenTestRows) Err() error  { return nil }
func (r *acceptedGenTestRows) Close() error { return nil }
