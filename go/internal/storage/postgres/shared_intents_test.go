package postgres

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestSharedIntentStoreUpsertAndList(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)
	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:         "si-1",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-1",
			RepositoryID:     "repository:r_payments",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{"fact_count": 3},
			CreatedAt:        now,
		},
	}

	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("UpsertIntents: %v", err)
	}

	got, err := store.ListIntents(ctx, SharedIntentFilter{
		RepositoryID: "repository:r_payments",
		SourceRunID:  "run-001",
		Limit:        100,
	})
	if err != nil {
		t.Fatalf("ListIntents: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1", len(got))
	}
	if got[0].IntentID != "si-1" {
		t.Errorf("IntentID = %q", got[0].IntentID)
	}
	if got[0].ProjectionDomain != reducer.DomainPlatformInfra {
		t.Errorf("ProjectionDomain = %q", got[0].ProjectionDomain)
	}
}

func TestSharedIntentStoreUpsertOverwrites(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)
	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:         "si-upsert",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-1",
			RepositoryID:     "repository:r_api",
			SourceRunID:      "run-002",
			GenerationID:     "gen-002",
			Payload:          map[string]any{"version": "v1"},
			CreatedAt:        now,
		},
	}

	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("first UpsertIntents: %v", err)
	}

	rows[0].Payload = map[string]any{"version": "v2"}
	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("second UpsertIntents: %v", err)
	}

	got, err := store.ListIntents(ctx, SharedIntentFilter{
		RepositoryID: "repository:r_api",
		SourceRunID:  "run-002",
		Limit:        100,
	})
	if err != nil {
		t.Fatalf("ListIntents: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1", len(got))
	}
	if got[0].Payload["version"] != "v2" {
		t.Errorf("Payload version = %v, want v2 after upsert", got[0].Payload["version"])
	}
}

func TestSharedIntentStoreListPendingDomainIntents(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)
	completed := now.Add(-time.Hour)

	pending := reducer.SharedProjectionIntentRow{
		IntentID:         "si-pending",
		ProjectionDomain: reducer.DomainPlatformInfra,
		PartitionKey:     "pk-1",
		RepositoryID:     "repository:r_pending",
		SourceRunID:      "run-p",
		GenerationID:     "gen-p",
		Payload:          map[string]any{},
		CreatedAt:        now,
		CompletedAt:      nil,
	}
	done := reducer.SharedProjectionIntentRow{
		IntentID:         "si-done",
		ProjectionDomain: reducer.DomainPlatformInfra,
		PartitionKey:     "pk-2",
		RepositoryID:     "repository:r_done",
		SourceRunID:      "run-d",
		GenerationID:     "gen-d",
		Payload:          map[string]any{},
		CreatedAt:        now,
		CompletedAt:      &completed,
	}

	if err := store.UpsertIntents(ctx, []reducer.SharedProjectionIntentRow{pending, done}); err != nil {
		t.Fatalf("UpsertIntents: %v", err)
	}

	got, err := store.ListPendingDomainIntents(ctx, reducer.DomainPlatformInfra, 100)
	if err != nil {
		t.Fatalf("ListPendingDomainIntents: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("len = %d, want 1", len(got))
	}
	if got[0].IntentID != "si-pending" {
		t.Errorf("IntentID = %q, want si-pending", got[0].IntentID)
	}
}

func TestSharedIntentStoreMarkIntentsCompleted(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)
	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:         "si-mark-1",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-1",
			RepositoryID:     "repository:r_mark",
			SourceRunID:      "run-m",
			GenerationID:     "gen-m",
			Payload:          map[string]any{},
			CreatedAt:        now,
		},
	}

	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("UpsertIntents: %v", err)
	}

	completedAt := now.Add(time.Minute)
	if err := store.MarkIntentsCompleted(ctx, []string{"si-mark-1"}, completedAt); err != nil {
		t.Fatalf("MarkIntentsCompleted: %v", err)
	}

	// Verify it no longer appears in pending.
	got, err := store.ListPendingDomainIntents(ctx, reducer.DomainPlatformInfra, 100)
	if err != nil {
		t.Fatalf("ListPendingDomainIntents: %v", err)
	}
	if len(got) != 0 {
		t.Errorf("expected 0 pending after mark completed, got %d", len(got))
	}

	// Verify it still appears in ListIntents with completed_at set.
	all, err := store.ListIntents(ctx, SharedIntentFilter{
		RepositoryID: "repository:r_mark",
		SourceRunID:  "run-m",
		Limit:        100,
	})
	if err != nil {
		t.Fatalf("ListIntents: %v", err)
	}
	if len(all) != 1 {
		t.Fatalf("len = %d, want 1", len(all))
	}
	if all[0].CompletedAt == nil {
		t.Error("CompletedAt should be set after MarkIntentsCompleted")
	}
}

func TestSharedIntentStoreEmptyUpsertIsNoop(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	if err := store.UpsertIntents(ctx, nil); err != nil {
		t.Fatalf("UpsertIntents(nil): %v", err)
	}
	if err := store.UpsertIntents(ctx, []reducer.SharedProjectionIntentRow{}); err != nil {
		t.Fatalf("UpsertIntents(empty): %v", err)
	}
}

func TestSharedIntentSchemaSQL(t *testing.T) {
	t.Parallel()

	sqlStr := SharedIntentSchemaSQL()
	if !strings.Contains(sqlStr, "CREATE TABLE IF NOT EXISTS shared_projection_intents") {
		t.Error("missing shared_projection_intents table")
	}
	if !strings.Contains(sqlStr, "CREATE TABLE IF NOT EXISTS shared_projection_partition_leases") {
		t.Error("missing shared_projection_partition_leases table")
	}
	if !strings.Contains(sqlStr, "shared_projection_intents_repo_run_idx") {
		t.Error("missing repo_run index")
	}
	if !strings.Contains(sqlStr, "shared_projection_intents_pending_idx") {
		t.Error("missing pending index")
	}
}

// -- test helpers --

// sharedIntentTestDB is an in-memory mock of ExecQueryer that stores shared
// projection intents for unit testing. Follows the decisionTestDB pattern.
type sharedIntentTestDB struct {
	intents map[string]reducer.SharedProjectionIntentRow
}

func newSharedIntentTestDB() *sharedIntentTestDB {
	return &sharedIntentTestDB{
		intents: make(map[string]reducer.SharedProjectionIntentRow),
	}
}

func (db *sharedIntentTestDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	switch {
	case strings.Contains(query, "INSERT INTO shared_projection_intents"):
		row := reducer.SharedProjectionIntentRow{
			IntentID:         args[0].(string),
			ProjectionDomain: args[1].(string),
			PartitionKey:     args[2].(string),
			RepositoryID:     args[3].(string),
			SourceRunID:      args[4].(string),
			GenerationID:     args[5].(string),
			CreatedAt:        args[7].(time.Time),
		}
		if b, ok := args[6].([]byte); ok {
			var m map[string]any
			if err := json.Unmarshal(b, &m); err == nil {
				row.Payload = m
			}
		}
		if args[8] != nil {
			ca := args[8].(time.Time)
			row.CompletedAt = &ca
		}
		db.intents[row.IntentID] = row
		return sharedIntentResult{}, nil

	case strings.Contains(query, "UPDATE shared_projection_intents"):
		completedAt := args[0].(time.Time)
		for i := 1; i < len(args); i++ {
			id := args[i].(string)
			if row, ok := db.intents[id]; ok {
				row.CompletedAt = &completedAt
				db.intents[id] = row
			}
		}
		return sharedIntentResult{}, nil

	case strings.Contains(query, "CREATE TABLE") || strings.Contains(query, "CREATE INDEX"):
		return sharedIntentResult{}, nil

	default:
		return nil, fmt.Errorf("unexpected exec query: %s", query)
	}
}

func (db *sharedIntentTestDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	switch {
	case strings.Contains(query, "completed_at IS NULL"):
		// ListPendingDomainIntents
		domain := args[0].(string)
		limit := args[1].(int)
		if limit < 1 {
			limit = 1
		}

		var rows [][]any
		for _, intent := range db.intents {
			if intent.ProjectionDomain != domain {
				continue
			}
			if intent.CompletedAt != nil {
				continue
			}
			payloadBytes, _ := json.Marshal(intent.Payload)
			rows = append(rows, []any{
				intent.IntentID,
				intent.ProjectionDomain,
				intent.PartitionKey,
				intent.RepositoryID,
				intent.SourceRunID,
				intent.GenerationID,
				payloadBytes,
				intent.CreatedAt,
				nil,
			})
			if len(rows) >= limit {
				break
			}
		}
		return newSharedIntentRows(rows), nil

	case strings.Contains(query, "FROM shared_projection_intents"):
		// ListIntents
		repoID := args[0].(string)
		runID := args[1].(string)
		var projDomain *string
		if s, ok := args[2].(string); ok && s != "" {
			projDomain = &s
		}
		limit := args[3].(int)
		if limit < 1 {
			limit = 1
		}

		var rows [][]any
		for _, intent := range db.intents {
			if intent.RepositoryID != repoID || intent.SourceRunID != runID {
				continue
			}
			if projDomain != nil && intent.ProjectionDomain != *projDomain {
				continue
			}
			payloadBytes, _ := json.Marshal(intent.Payload)
			var completedAt any
			if intent.CompletedAt != nil {
				completedAt = *intent.CompletedAt
			}
			rows = append(rows, []any{
				intent.IntentID,
				intent.ProjectionDomain,
				intent.PartitionKey,
				intent.RepositoryID,
				intent.SourceRunID,
				intent.GenerationID,
				payloadBytes,
				intent.CreatedAt,
				completedAt,
			})
			if len(rows) >= limit {
				break
			}
		}
		return newSharedIntentRows(rows), nil

	default:
		return nil, fmt.Errorf("unexpected query: %s", query)
	}
}

type sharedIntentResult struct{}

func (sharedIntentResult) LastInsertId() (int64, error) { return 0, nil }
func (sharedIntentResult) RowsAffected() (int64, error) { return 1, nil }

// sharedIntentRows implements the Rows interface for shared intent test queries.
type sharedIntentRows struct {
	data [][]any
	idx  int
}

func newSharedIntentRows(data [][]any) *sharedIntentRows {
	return &sharedIntentRows{data: data, idx: -1}
}

func (r *sharedIntentRows) Next() bool {
	r.idx++
	return r.idx < len(r.data)
}

func (r *sharedIntentRows) Scan(dest ...any) error {
	if r.idx < 0 || r.idx >= len(r.data) {
		return fmt.Errorf("scan out of range")
	}
	row := r.data[r.idx]
	if len(dest) != len(row) {
		return fmt.Errorf("scan: got %d dest, have %d cols", len(dest), len(row))
	}
	for i, val := range row {
		switch d := dest[i].(type) {
		case *string:
			if val == nil {
				*d = ""
			} else {
				*d = val.(string)
			}
		case *time.Time:
			*d = val.(time.Time)
		case *[]byte:
			if b, ok := val.([]byte); ok {
				*d = b
			}
		case *sql.NullTime:
			if val == nil {
				d.Valid = false
			} else {
				d.Time = val.(time.Time)
				d.Valid = true
			}
		default:
			return fmt.Errorf("unsupported scan dest type %T", dest[i])
		}
	}
	return nil
}

func (r *sharedIntentRows) Err() error  { return nil }
func (r *sharedIntentRows) Close() error { return nil }

// -- partition lease tests --

func TestSharedIntentStoreClaimPartitionLease(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name           string
		existingLease  *partitionLeaseRow
		domain         string
		partitionID    int
		partitionCount int
		leaseOwner     string
		leaseTTL       time.Duration
		wantClaimed    bool
		wantErr        bool
	}{
		{
			name:           "claim new lease",
			existingLease:  nil,
			domain:         "platform-infra",
			partitionID:    0,
			partitionCount: 4,
			leaseOwner:     "worker-1",
			leaseTTL:       30 * time.Second,
			wantClaimed:    true,
			wantErr:        false,
		},
		{
			name: "claim expired lease",
			existingLease: &partitionLeaseRow{
				projectionDomain: "platform-infra",
				partitionID:      0,
				partitionCount:   4,
				leaseOwner:       stringPtr("worker-2"),
				leaseExpiresAt:   timePtr(time.Now().UTC().Add(-5 * time.Minute)),
				updatedAt:        time.Now().UTC().Add(-5 * time.Minute),
			},
			domain:         "platform-infra",
			partitionID:    0,
			partitionCount: 4,
			leaseOwner:     "worker-1",
			leaseTTL:       30 * time.Second,
			wantClaimed:    true,
			wantErr:        false,
		},
		{
			name: "reclaim own lease",
			existingLease: &partitionLeaseRow{
				projectionDomain: "platform-infra",
				partitionID:      0,
				partitionCount:   4,
				leaseOwner:       stringPtr("worker-1"),
				leaseExpiresAt:   timePtr(time.Now().UTC().Add(5 * time.Minute)),
				updatedAt:        time.Now().UTC(),
			},
			domain:         "platform-infra",
			partitionID:    0,
			partitionCount: 4,
			leaseOwner:     "worker-1",
			leaseTTL:       30 * time.Second,
			wantClaimed:    true,
			wantErr:        false,
		},
		{
			name: "cannot claim active lease owned by other",
			existingLease: &partitionLeaseRow{
				projectionDomain: "platform-infra",
				partitionID:      0,
				partitionCount:   4,
				leaseOwner:       stringPtr("worker-2"),
				leaseExpiresAt:   timePtr(time.Now().UTC().Add(5 * time.Minute)),
				updatedAt:        time.Now().UTC(),
			},
			domain:         "platform-infra",
			partitionID:    0,
			partitionCount: 4,
			leaseOwner:     "worker-1",
			leaseTTL:       30 * time.Second,
			wantClaimed:    false,
			wantErr:        false,
		},
		{
			name: "claim released lease",
			existingLease: &partitionLeaseRow{
				projectionDomain: "platform-infra",
				partitionID:      0,
				partitionCount:   4,
				leaseOwner:       nil,
				leaseExpiresAt:   nil,
				updatedAt:        time.Now().UTC().Add(-1 * time.Minute),
			},
			domain:         "platform-infra",
			partitionID:    0,
			partitionCount: 4,
			leaseOwner:     "worker-1",
			leaseTTL:       30 * time.Second,
			wantClaimed:    true,
			wantErr:        false,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			db := newLeaseTestDB()
			if tt.existingLease != nil {
				db.leases[leaseKey{
					projectionDomain: tt.existingLease.projectionDomain,
					partitionID:      tt.existingLease.partitionID,
					partitionCount:   tt.existingLease.partitionCount,
				}] = *tt.existingLease
			}

			store := NewSharedIntentStore(db)
			ctx := context.Background()

			claimed, err := store.ClaimPartitionLease(
				ctx, tt.domain, tt.partitionID, tt.partitionCount,
				tt.leaseOwner, tt.leaseTTL,
			)

			if (err != nil) != tt.wantErr {
				t.Fatalf("ClaimPartitionLease error = %v, wantErr %v", err, tt.wantErr)
			}
			if claimed != tt.wantClaimed {
				t.Errorf("ClaimPartitionLease claimed = %v, want %v", claimed, tt.wantClaimed)
			}
		})
	}
}

func TestSharedIntentStoreReleasePartitionLease(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name           string
		existingLease  *partitionLeaseRow
		domain         string
		partitionID    int
		partitionCount int
		leaseOwner     string
		wantErr        bool
	}{
		{
			name: "release owned lease",
			existingLease: &partitionLeaseRow{
				projectionDomain: "dependency-map",
				partitionID:      2,
				partitionCount:   8,
				leaseOwner:       stringPtr("worker-1"),
				leaseExpiresAt:   timePtr(time.Now().UTC().Add(5 * time.Minute)),
				updatedAt:        time.Now().UTC(),
			},
			domain:         "dependency-map",
			partitionID:    2,
			partitionCount: 8,
			leaseOwner:     "worker-1",
			wantErr:        false,
		},
		{
			name: "release non-existent lease is noop",
			existingLease: nil,
			domain:         "dependency-map",
			partitionID:    2,
			partitionCount: 8,
			leaseOwner:     "worker-1",
			wantErr:        false,
		},
		{
			name: "release lease owned by other is noop",
			existingLease: &partitionLeaseRow{
				projectionDomain: "dependency-map",
				partitionID:      2,
				partitionCount:   8,
				leaseOwner:       stringPtr("worker-2"),
				leaseExpiresAt:   timePtr(time.Now().UTC().Add(5 * time.Minute)),
				updatedAt:        time.Now().UTC(),
			},
			domain:         "dependency-map",
			partitionID:    2,
			partitionCount: 8,
			leaseOwner:     "worker-1",
			wantErr:        false,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			db := newLeaseTestDB()
			if tt.existingLease != nil {
				db.leases[leaseKey{
					projectionDomain: tt.existingLease.projectionDomain,
					partitionID:      tt.existingLease.partitionID,
					partitionCount:   tt.existingLease.partitionCount,
				}] = *tt.existingLease
			}

			store := NewSharedIntentStore(db)
			ctx := context.Background()

			err := store.ReleasePartitionLease(
				ctx, tt.domain, tt.partitionID, tt.partitionCount, tt.leaseOwner,
			)

			if (err != nil) != tt.wantErr {
				t.Fatalf("ReleasePartitionLease error = %v, wantErr %v", err, tt.wantErr)
			}

			// Verify lease is released if we owned it
			if tt.existingLease != nil && tt.existingLease.leaseOwner != nil && *tt.existingLease.leaseOwner == tt.leaseOwner {
				k := leaseKey{
					projectionDomain: tt.domain,
					partitionID:      tt.partitionID,
					partitionCount:   tt.partitionCount,
				}
				if lease, ok := db.leases[k]; ok {
					if lease.leaseOwner != nil {
						t.Errorf("lease owner should be nil after release, got %v", *lease.leaseOwner)
					}
					if lease.leaseExpiresAt != nil {
						t.Errorf("lease expiry should be nil after release, got %v", *lease.leaseExpiresAt)
					}
				}
			}
		})
	}
}

// -- partition lease test helpers --

type leaseKey struct {
	projectionDomain string
	partitionID      int
	partitionCount   int
}

type partitionLeaseRow struct {
	projectionDomain string
	partitionID      int
	partitionCount   int
	leaseOwner       *string
	leaseExpiresAt   *time.Time
	updatedAt        time.Time
}

type leaseTestDB struct {
	leases map[leaseKey]partitionLeaseRow
}

func newLeaseTestDB() *leaseTestDB {
	return &leaseTestDB{
		leases: make(map[leaseKey]partitionLeaseRow),
	}
}

func (db *leaseTestDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	switch {
	case strings.Contains(query, "UPDATE shared_projection_partition_leases"):
		// Release lease
		domain := args[0].(string)
		partID := args[1].(int)
		partCount := args[2].(int)
		owner := args[3].(string)
		updatedAt := args[4].(time.Time)

		k := leaseKey{
			projectionDomain: domain,
			partitionID:      partID,
			partitionCount:   partCount,
		}

		if lease, ok := db.leases[k]; ok {
			if lease.leaseOwner != nil && *lease.leaseOwner == owner {
				lease.leaseOwner = nil
				lease.leaseExpiresAt = nil
				lease.updatedAt = updatedAt
				db.leases[k] = lease
			}
		}
		return sharedIntentResult{}, nil

	case strings.Contains(query, "CREATE TABLE") || strings.Contains(query, "CREATE INDEX"):
		return sharedIntentResult{}, nil

	default:
		return nil, fmt.Errorf("unexpected exec query: %s", query)
	}
}

func (db *leaseTestDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	if strings.Contains(query, "INSERT INTO shared_projection_partition_leases") {
		// Claim lease
		domain := args[0].(string)
		partID := args[1].(int)
		partCount := args[2].(int)
		owner := args[3].(string)
		expiresAt := args[4].(time.Time)
		updatedAt := args[5].(time.Time)

		k := leaseKey{
			projectionDomain: domain,
			partitionID:      partID,
			partitionCount:   partCount,
		}

		existingLease, exists := db.leases[k]

		// Check if we can claim the lease
		canClaim := false
		if !exists {
			// No existing lease
			canClaim = true
		} else if existingLease.leaseExpiresAt == nil {
			// Lease is released
			canClaim = true
		} else if existingLease.leaseExpiresAt.Before(updatedAt) || existingLease.leaseExpiresAt.Equal(updatedAt) {
			// Lease is expired
			canClaim = true
		} else if existingLease.leaseOwner != nil && *existingLease.leaseOwner == owner {
			// We already own this lease
			canClaim = true
		}

		if canClaim {
			db.leases[k] = partitionLeaseRow{
				projectionDomain: domain,
				partitionID:      partID,
				partitionCount:   partCount,
				leaseOwner:       &owner,
				leaseExpiresAt:   &expiresAt,
				updatedAt:        updatedAt,
			}
			return &leaseResultRows{
				data: [][]any{{domain}},
				idx:  -1,
			}, nil
		}

		return &leaseResultRows{data: nil, idx: -1}, nil
	}

	return nil, fmt.Errorf("unexpected query: %s", query)
}

type leaseResultRows struct {
	data [][]any
	idx  int
}

func (r *leaseResultRows) Next() bool {
	r.idx++
	return r.idx < len(r.data)
}

func (r *leaseResultRows) Scan(dest ...any) error {
	if r.idx < 0 || r.idx >= len(r.data) {
		return sql.ErrNoRows
	}
	row := r.data[r.idx]
	if len(dest) != len(row) {
		return fmt.Errorf("scan: got %d dest, have %d cols", len(dest), len(row))
	}
	for i, val := range row {
		if s, ok := dest[i].(*string); ok {
			*s = val.(string)
		} else {
			return fmt.Errorf("unsupported dest type %T", dest[i])
		}
	}
	return nil
}

func (r *leaseResultRows) Err() error  { return nil }
func (r *leaseResultRows) Close() error { return nil }

func stringPtr(s string) *string {
	return &s
}

func timePtr(t time.Time) *time.Time {
	return &t
}
