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

func TestSharedIntentStoreUpsertIntentsBatch(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)

	// Create 1200 intents to test batching (should result in 3 batches of 500, 500, 200)
	rows := make([]reducer.SharedProjectionIntentRow, 1200)
	for i := 0; i < 1200; i++ {
		rows[i] = reducer.SharedProjectionIntentRow{
			IntentID:         fmt.Sprintf("si-batch-%d", i),
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     fmt.Sprintf("pk-%d", i%10),
			RepositoryID:     "repository:r_batch_test",
			SourceRunID:      "run-batch",
			GenerationID:     "gen-batch",
			Payload:          map[string]any{"index": i},
			CreatedAt:        now,
		}
	}

	// Track exec calls before
	execCallsBefore := db.execCalls

	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("UpsertIntents: %v", err)
	}

	// Verify batching: 1200 intents should use 3 ExecContext calls (batches of 500, 500, 200)
	// not 1200 calls
	execCallsAfter := db.execCalls
	batchCallsUsed := execCallsAfter - execCallsBefore

	expectedBatches := 3 // ceil(1200 / 500) = 3
	if batchCallsUsed != expectedBatches {
		t.Errorf("expected %d batch ExecContext calls, got %d (1200 intents should batch)", expectedBatches, batchCallsUsed)
	}

	// Verify all intents were stored
	if len(db.intents) != 1200 {
		t.Errorf("expected 1200 intents stored, got %d", len(db.intents))
	}

	// Spot-check a few intents
	for _, idx := range []int{0, 500, 999, 1199} {
		intentID := fmt.Sprintf("si-batch-%d", idx)
		intent, ok := db.intents[intentID]
		if !ok {
			t.Errorf("intent %q not found", intentID)
			continue
		}
		if intent.RepositoryID != "repository:r_batch_test" {
			t.Errorf("intent %q: RepositoryID = %q", intentID, intent.RepositoryID)
		}
		if payloadIdx, ok := intent.Payload["index"].(float64); !ok || int(payloadIdx) != idx {
			t.Errorf("intent %q: Payload index = %v, want %d", intentID, intent.Payload["index"], idx)
		}
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

func TestSharedIntentStoreListPendingRepoRunIntents(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)
	completed := now.Add(-time.Hour)

	// Create multiple intents with different states
	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:         "si-pending-1",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-1",
			RepositoryID:     "repository:r_test",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{"fact_count": 5},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
		{
			IntentID:         "si-pending-2",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-2",
			RepositoryID:     "repository:r_test",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{"fact_count": 3},
			CreatedAt:        now.Add(time.Second),
			CompletedAt:      nil,
		},
		{
			IntentID:         "si-completed",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-3",
			RepositoryID:     "repository:r_test",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{"fact_count": 2},
			CreatedAt:        now,
			CompletedAt:      &completed,
		},
		{
			IntentID:         "si-different-run",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-4",
			RepositoryID:     "repository:r_test",
			SourceRunID:      "run-002",
			GenerationID:     "gen-002",
			Payload:          map[string]any{"fact_count": 1},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
		{
			IntentID:         "si-different-domain",
			ProjectionDomain: "dependency-map",
			PartitionKey:     "pk-5",
			RepositoryID:     "repository:r_test",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{"fact_count": 1},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
	}

	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("UpsertIntents: %v", err)
	}

	// Test 1: Returns matching pending intents
	got, err := store.ListPendingRepoRunIntents(ctx, "repository:r_test", "run-001", reducer.DomainPlatformInfra, 100)
	if err != nil {
		t.Fatalf("ListPendingRepoRunIntents: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("len = %d, want 2 (only pending intents for repo/run/domain)", len(got))
	}
	foundIDs := map[string]bool{}
	for _, intent := range got {
		foundIDs[intent.IntentID] = true
	}
	if !foundIDs["si-pending-1"] || !foundIDs["si-pending-2"] {
		t.Errorf("expected to find si-pending-1 and si-pending-2, got %v", foundIDs)
	}

	// Test 2: Returns empty for non-matching repo/run
	got, err = store.ListPendingRepoRunIntents(ctx, "repository:r_different", "run-001", reducer.DomainPlatformInfra, 100)
	if err != nil {
		t.Fatalf("ListPendingRepoRunIntents (non-matching): %v", err)
	}
	if len(got) != 0 {
		t.Errorf("expected 0 results for non-matching repo, got %d", len(got))
	}

	// Test 3: Returns empty for non-matching domain
	got, err = store.ListPendingRepoRunIntents(ctx, "repository:r_test", "run-001", "non-existent-domain", 100)
	if err != nil {
		t.Fatalf("ListPendingRepoRunIntents (non-matching domain): %v", err)
	}
	if len(got) != 0 {
		t.Errorf("expected 0 results for non-matching domain, got %d", len(got))
	}
}

func TestSharedIntentStoreCountPendingGenerationIntents(t *testing.T) {
	t.Parallel()

	db := newSharedIntentTestDB()
	store := NewSharedIntentStore(db)
	ctx := context.Background()

	now := time.Now().UTC().Truncate(time.Microsecond)
	completed := now.Add(-time.Hour)

	// Create multiple intents with different states
	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:         "si-gen-pending-1",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-1",
			RepositoryID:     "repository:r_count",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
		{
			IntentID:         "si-gen-pending-2",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-2",
			RepositoryID:     "repository:r_count",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
		{
			IntentID:         "si-gen-pending-3",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-3",
			RepositoryID:     "repository:r_count",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
		{
			IntentID:         "si-gen-completed",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-4",
			RepositoryID:     "repository:r_count",
			SourceRunID:      "run-001",
			GenerationID:     "gen-001",
			Payload:          map[string]any{},
			CreatedAt:        now,
			CompletedAt:      &completed,
		},
		{
			IntentID:         "si-gen-different-gen",
			ProjectionDomain: reducer.DomainPlatformInfra,
			PartitionKey:     "pk-5",
			RepositoryID:     "repository:r_count",
			SourceRunID:      "run-001",
			GenerationID:     "gen-002",
			Payload:          map[string]any{},
			CreatedAt:        now,
			CompletedAt:      nil,
		},
	}

	if err := store.UpsertIntents(ctx, rows); err != nil {
		t.Fatalf("UpsertIntents: %v", err)
	}

	// Test 1: Returns correct count when pending intents exist
	count, err := store.CountPendingGenerationIntents(ctx, "repository:r_count", "run-001", "gen-001", reducer.DomainPlatformInfra)
	if err != nil {
		t.Fatalf("CountPendingGenerationIntents: %v", err)
	}
	if count != 3 {
		t.Errorf("count = %d, want 3 (pending intents for gen-001)", count)
	}

	// Test 2: Returns 0 when no pending intents
	count, err = store.CountPendingGenerationIntents(ctx, "repository:r_different", "run-001", "gen-001", reducer.DomainPlatformInfra)
	if err != nil {
		t.Fatalf("CountPendingGenerationIntents (non-matching): %v", err)
	}
	if count != 0 {
		t.Errorf("count = %d, want 0 for non-matching repo", count)
	}

	// Test 3: Returns 0 for non-matching generation
	count, err = store.CountPendingGenerationIntents(ctx, "repository:r_count", "run-001", "gen-999", reducer.DomainPlatformInfra)
	if err != nil {
		t.Fatalf("CountPendingGenerationIntents (non-matching gen): %v", err)
	}
	if count != 0 {
		t.Errorf("count = %d, want 0 for non-matching generation", count)
	}
}

// -- test helpers --

// sharedIntentTestDB is an in-memory mock of ExecQueryer that stores shared
// projection intents for unit testing. Follows the decisionTestDB pattern.
type sharedIntentTestDB struct {
	intents   map[string]reducer.SharedProjectionIntentRow
	execCalls int
}

func newSharedIntentTestDB() *sharedIntentTestDB {
	return &sharedIntentTestDB{
		intents: make(map[string]reducer.SharedProjectionIntentRow),
	}
}

func (db *sharedIntentTestDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	db.execCalls++

	switch {
	case strings.Contains(query, "INSERT INTO shared_projection_intents"):
		// Handle batched multi-row INSERT
		// Each row has 9 columns: intent_id, projection_domain, partition_key,
		// repository_id, source_run_id, generation_id, payload, created_at, completed_at
		numRows := len(args) / 9
		for i := 0; i < numRows; i++ {
			offset := i * 9
			row := reducer.SharedProjectionIntentRow{
				IntentID:         args[offset+0].(string),
				ProjectionDomain: args[offset+1].(string),
				PartitionKey:     args[offset+2].(string),
				RepositoryID:     args[offset+3].(string),
				SourceRunID:      args[offset+4].(string),
				GenerationID:     args[offset+5].(string),
				CreatedAt:        args[offset+7].(time.Time),
			}
			if b, ok := args[offset+6].([]byte); ok {
				var m map[string]any
				if err := json.Unmarshal(b, &m); err == nil {
					row.Payload = m
				}
			}
			if args[offset+8] != nil {
				ca := args[offset+8].(time.Time)
				row.CompletedAt = &ca
			}
			db.intents[row.IntentID] = row
		}
		return sharedIntentResult{}, nil

	case strings.Contains(query, "UPDATE shared_projection_intents"):
		completedAt := args[0].(time.Time)
		intentIDs := args[1].([]string)
		for _, id := range intentIDs {
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
	case strings.Contains(query, "SELECT COUNT(*)"):
		// CountPendingGenerationIntents
		repoID := args[0].(string)
		runID := args[1].(string)
		genID := args[2].(string)
		domain := args[3].(string)

		count := 0
		for _, intent := range db.intents {
			if intent.RepositoryID == repoID &&
				intent.SourceRunID == runID &&
				intent.GenerationID == genID &&
				intent.ProjectionDomain == domain &&
				intent.CompletedAt == nil {
				count++
			}
		}
		return &countResultRows{count: count}, nil

	case strings.Contains(query, "projection_domain = $3") && strings.Contains(query, "completed_at IS NULL"):
		// ListPendingRepoRunIntents
		repoID := args[0].(string)
		runID := args[1].(string)
		domain := args[2].(string)
		limit := args[3].(int)
		if limit < 1 {
			limit = 1
		}

		var rows [][]any
		for _, intent := range db.intents {
			if intent.RepositoryID != repoID {
				continue
			}
			if intent.SourceRunID != runID {
				continue
			}
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

func (r *sharedIntentRows) Err() error   { return nil }
func (r *sharedIntentRows) Close() error { return nil }

// countResultRows implements the Rows interface for COUNT queries.
type countResultRows struct {
	count   int
	scanned bool
}

func (r *countResultRows) Next() bool {
	if r.scanned {
		return false
	}
	r.scanned = true
	return true
}

func (r *countResultRows) Scan(dest ...any) error {
	if len(dest) != 1 {
		return fmt.Errorf("scan: expected 1 dest for COUNT, got %d", len(dest))
	}
	if intDest, ok := dest[0].(*int); ok {
		*intDest = r.count
		return nil
	}
	return fmt.Errorf("unsupported scan dest type %T for COUNT", dest[0])
}

func (r *countResultRows) Err() error   { return nil }
func (r *countResultRows) Close() error { return nil }

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
			name:           "release non-existent lease is noop",
			existingLease:  nil,
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

func (r *leaseResultRows) Err() error   { return nil }
func (r *leaseResultRows) Close() error { return nil }

func stringPtr(s string) *string {
	return &s
}

func timePtr(t time.Time) *time.Time {
	return &t
}
