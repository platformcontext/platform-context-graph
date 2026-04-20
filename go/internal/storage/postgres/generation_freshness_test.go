package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"testing"
)

func TestGenerationFreshnessCheck(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name         string
		scopeID      string
		generationID string
		db           *generationFreshnessTestDB
		wantCurrent  bool
		wantErr      bool
	}{
		{
			name:         "current when generation matches active",
			scopeID:      "scope-123",
			generationID: "gen-abc",
			db: &generationFreshnessTestDB{
				scopes: map[string]sql.NullString{
					"scope-123": {String: "gen-abc", Valid: true},
				},
			},
			wantCurrent: true,
		},
		{
			name:         "stale when generation does not match active",
			scopeID:      "scope-123",
			generationID: "gen-old",
			db: &generationFreshnessTestDB{
				scopes: map[string]sql.NullString{
					"scope-123": {String: "gen-new", Valid: true},
				},
			},
			wantCurrent: false,
		},
		{
			name:         "current when scope not found",
			scopeID:      "scope-unknown",
			generationID: "gen-abc",
			db: &generationFreshnessTestDB{
				scopes: map[string]sql.NullString{},
			},
			wantCurrent: true,
		},
		{
			name:         "current when active_generation_id is NULL",
			scopeID:      "scope-123",
			generationID: "gen-abc",
			db: &generationFreshnessTestDB{
				scopes: map[string]sql.NullString{
					"scope-123": {Valid: false},
				},
			},
			wantCurrent: true,
		},
		{
			name:         "error propagated from database",
			scopeID:      "scope-123",
			generationID: "gen-abc",
			db: &generationFreshnessTestDB{
				queryErr: fmt.Errorf("connection refused"),
			},
			wantCurrent: false,
			wantErr:     true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			check := NewGenerationFreshnessCheck(tt.db)
			gotCurrent, err := check(context.Background(), tt.scopeID, tt.generationID)

			if tt.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if gotCurrent != tt.wantCurrent {
				t.Fatalf("current = %v, want %v", gotCurrent, tt.wantCurrent)
			}
		})
	}
}

// -- test helpers --

type generationFreshnessTestDB struct {
	scopes   map[string]sql.NullString // scope_id -> active_generation_id
	queryErr error
}

func (db *generationFreshnessTestDB) ExecContext(_ context.Context, _ string, _ ...any) (sql.Result, error) {
	return nil, fmt.Errorf("ExecContext not implemented in test stub")
}

func (db *generationFreshnessTestDB) QueryContext(_ context.Context, _ string, args ...any) (Rows, error) {
	if db.queryErr != nil {
		return nil, db.queryErr
	}

	if len(args) != 1 {
		return nil, fmt.Errorf("expected 1 arg, got %d", len(args))
	}

	scopeID := args[0].(string)
	activeGen, found := db.scopes[scopeID]
	if !found {
		return &generationFreshnessTestRows{data: nil, idx: -1}, nil
	}

	return &generationFreshnessTestRows{
		data: []sql.NullString{activeGen},
		idx:  -1,
	}, nil
}

type generationFreshnessTestRows struct {
	data []sql.NullString
	idx  int
}

func (r *generationFreshnessTestRows) Next() bool {
	r.idx++
	return r.idx < len(r.data)
}

func (r *generationFreshnessTestRows) Scan(dest ...any) error {
	if r.idx < 0 || r.idx >= len(r.data) {
		return sql.ErrNoRows
	}
	if len(dest) != 1 {
		return fmt.Errorf("scan: got %d dest, want 1", len(dest))
	}
	switch d := dest[0].(type) {
	case *sql.NullString:
		*d = r.data[r.idx]
	default:
		return fmt.Errorf("unsupported scan dest type %T", dest[0])
	}
	return nil
}

func (r *generationFreshnessTestRows) Err() error  { return nil }
func (r *generationFreshnessTestRows) Close() error { return nil }
