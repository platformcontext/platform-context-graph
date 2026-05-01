package postgres

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"testing"
	"time"
)

func TestIaCReachabilityStoreUpsertAndListCleanupFindings(t *testing.T) {
	t.Parallel()

	db := newIaCReachabilityTestDB()
	store := NewIaCReachabilityStore(db)
	ctx := context.Background()
	now := time.Now().UTC().Truncate(time.Microsecond)

	rows := []IaCReachabilityRow{
		{
			ScopeID:      "scope-1",
			GenerationID: "gen-1",
			RepoID:       "terraform-modules",
			Family:       "terraform",
			ArtifactPath: "modules/checkout-service",
			ArtifactName: "checkout-service",
			Reachability: IaCReachabilityUsed,
			Finding:      IaCFindingInUse,
			Confidence:   0.99,
			Evidence:     []string{"terraform-stack/main.tf: source modules/checkout-service"},
			ObservedAt:   now,
			UpdatedAt:    now,
		},
		{
			ScopeID:      "scope-1",
			GenerationID: "gen-1",
			RepoID:       "terraform-modules",
			Family:       "terraform",
			ArtifactPath: "modules/orphan-cache",
			ArtifactName: "orphan-cache",
			Reachability: IaCReachabilityUnused,
			Finding:      IaCFindingCandidateDead,
			Confidence:   0.75,
			Evidence:     []string{"module directory exists"},
			ObservedAt:   now,
			UpdatedAt:    now,
		},
		{
			ScopeID:      "scope-1",
			GenerationID: "gen-1",
			RepoID:       "terraform-modules",
			Family:       "terraform",
			ArtifactPath: "modules/dynamic-target",
			ArtifactName: "dynamic-target",
			Reachability: IaCReachabilityAmbiguous,
			Finding:      IaCFindingAmbiguousDynamic,
			Confidence:   0.40,
			Evidence:     []string{"terraform-stack/main.tf: dynamic source"},
			Limitations:  []string{"dynamic reference requires renderer evidence"},
			ObservedAt:   now,
			UpdatedAt:    now,
		},
	}

	if err := store.Upsert(ctx, rows); err != nil {
		t.Fatalf("Upsert: %v", err)
	}

	got, err := store.ListCleanupFindings(ctx, "scope-1", "gen-1", true, 100)
	if err != nil {
		t.Fatalf("ListCleanupFindings: %v", err)
	}
	if gotLen, wantLen := len(got), 2; gotLen != wantLen {
		t.Fatalf("len = %d, want %d: %#v", gotLen, wantLen, got)
	}
	if got[0].ArtifactName != "dynamic-target" {
		t.Fatalf("first artifact = %q, want dynamic-target", got[0].ArtifactName)
	}
	if got[0].Reachability != IaCReachabilityAmbiguous {
		t.Fatalf("first reachability = %q, want %q", got[0].Reachability, IaCReachabilityAmbiguous)
	}
	if got[1].ArtifactName != "orphan-cache" {
		t.Fatalf("second artifact = %q, want orphan-cache", got[1].ArtifactName)
	}

	withoutAmbiguous, err := store.ListCleanupFindings(ctx, "scope-1", "gen-1", false, 100)
	if err != nil {
		t.Fatalf("ListCleanupFindings without ambiguous: %v", err)
	}
	if gotLen, wantLen := len(withoutAmbiguous), 1; gotLen != wantLen {
		t.Fatalf("len without ambiguous = %d, want %d", gotLen, wantLen)
	}
	if withoutAmbiguous[0].Reachability != IaCReachabilityUnused {
		t.Fatalf("reachability without ambiguous = %q, want %q", withoutAmbiguous[0].Reachability, IaCReachabilityUnused)
	}
}

func TestIaCReachabilitySchemaSQL(t *testing.T) {
	t.Parallel()

	sqlStr := IaCReachabilitySchemaSQL()
	if !strings.Contains(sqlStr, "CREATE TABLE IF NOT EXISTS iac_reachability_rows") {
		t.Fatal("missing iac_reachability_rows table")
	}
	if !strings.Contains(sqlStr, "PRIMARY KEY (scope_id, generation_id, repo_id, family, artifact_path)") {
		t.Fatal("missing durable artifact primary key")
	}
	if !strings.Contains(sqlStr, "iac_reachability_cleanup_idx") {
		t.Fatal("missing cleanup lookup index")
	}
	if !strings.Contains(sqlStr, "evidence JSONB NOT NULL") {
		t.Fatal("missing evidence JSONB column")
	}
}

type iacReachabilityTestDB struct {
	rows map[string]iacReachabilityStoredRow
}

type iacReachabilityStoredRow struct {
	ScopeID      string
	GenerationID string
	RepoID       string
	Family       string
	ArtifactPath string
	ArtifactName string
	Reachability string
	Finding      string
	Confidence   float64
	Evidence     []string
	Limitations  []string
	ObservedAt   time.Time
	UpdatedAt    time.Time
}

func newIaCReachabilityTestDB() *iacReachabilityTestDB {
	return &iacReachabilityTestDB{rows: map[string]iacReachabilityStoredRow{}}
}

func (db *iacReachabilityTestDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	switch {
	case strings.Contains(query, "INSERT INTO iac_reachability_rows"):
		const columnsPerRow = 13
		for i := 0; i < len(args); i += columnsPerRow {
			evidence, err := decodeStringArrayJSON(args[i+9])
			if err != nil {
				return nil, err
			}
			limitations, err := decodeStringArrayJSON(args[i+10])
			if err != nil {
				return nil, err
			}
			row := iacReachabilityStoredRow{
				ScopeID:      args[i+0].(string),
				GenerationID: args[i+1].(string),
				RepoID:       args[i+2].(string),
				Family:       args[i+3].(string),
				ArtifactPath: args[i+4].(string),
				ArtifactName: args[i+5].(string),
				Reachability: args[i+6].(string),
				Finding:      args[i+7].(string),
				Confidence:   args[i+8].(float64),
				Evidence:     evidence,
				Limitations:  limitations,
				ObservedAt:   args[i+11].(time.Time),
				UpdatedAt:    args[i+12].(time.Time),
			}
			db.rows[iacReachabilityKey(row)] = row
		}
		return sharedIntentResult{}, nil

	case strings.Contains(query, "CREATE TABLE") || strings.Contains(query, "CREATE INDEX"):
		return sharedIntentResult{}, nil

	default:
		return nil, fmt.Errorf("unexpected exec query: %s", query)
	}
}

func (db *iacReachabilityTestDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	if !strings.Contains(query, "FROM iac_reachability_rows") {
		return nil, fmt.Errorf("unexpected query: %s", query)
	}
	scopeID := args[0].(string)
	generationID := args[1].(string)
	includeAmbiguous := args[2].(bool)
	limit := args[3].(int)

	var matches [][]any
	for _, row := range db.rows {
		if row.ScopeID != scopeID || row.GenerationID != generationID {
			continue
		}
		switch row.Reachability {
		case string(IaCReachabilityUnused):
		case string(IaCReachabilityAmbiguous):
			if !includeAmbiguous {
				continue
			}
		default:
			continue
		}
		evidence, _ := json.Marshal(row.Evidence)
		limitations, _ := json.Marshal(row.Limitations)
		matches = append(matches, []any{
			row.ScopeID, row.GenerationID, row.RepoID, row.Family,
			row.ArtifactPath, row.ArtifactName, row.Reachability, row.Finding,
			row.Confidence, evidence, limitations, row.ObservedAt, row.UpdatedAt,
		})
	}
	sort.Slice(matches, func(i, j int) bool {
		leftFamily := matches[i][3].(string)
		rightFamily := matches[j][3].(string)
		if leftFamily != rightFamily {
			return leftFamily < rightFamily
		}
		return matches[i][4].(string) < matches[j][4].(string)
	})
	if len(matches) > limit {
		matches = matches[:limit]
	}
	return &iacReachabilityRows{data: matches, idx: -1}, nil
}

type iacReachabilityRows struct {
	data [][]any
	idx  int
}

func (r *iacReachabilityRows) Next() bool {
	r.idx++
	return r.idx < len(r.data)
}

func (r *iacReachabilityRows) Scan(dest ...any) error {
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
			*d = val.(string)
		case *float64:
			*d = val.(float64)
		case *[]byte:
			*d = val.([]byte)
		case *time.Time:
			*d = val.(time.Time)
		default:
			return fmt.Errorf("unsupported scan dest type %T", dest[i])
		}
	}
	return nil
}

func (r *iacReachabilityRows) Err() error   { return nil }
func (r *iacReachabilityRows) Close() error { return nil }

func iacReachabilityKey(row iacReachabilityStoredRow) string {
	return strings.Join([]string{row.ScopeID, row.GenerationID, row.RepoID, row.Family, row.ArtifactPath}, "|")
}

func decodeStringArrayJSON(raw any) ([]string, error) {
	bytes, ok := raw.([]byte)
	if !ok {
		return nil, fmt.Errorf("json arg type = %T, want []byte", raw)
	}
	var out []string
	if err := json.Unmarshal(bytes, &out); err != nil {
		return nil, err
	}
	return out, nil
}
