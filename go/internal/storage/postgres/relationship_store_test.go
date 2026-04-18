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

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestRelationshipStoreUpsertAndListAssertions(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	assertions := []relationships.Assertion{
		{
			SourceRepoID:     "repo-infra",
			TargetRepoID:     "repo-api",
			RelationshipType: relationships.RelProvisionsDependencyFor,
			Decision:         "assert",
			Reason:           "known provisioning link",
			Actor:            "admin",
		},
	}

	if err := store.UpsertAssertions(ctx, assertions); err != nil {
		t.Fatalf("UpsertAssertions: %v", err)
	}

	result, err := store.ListAssertions(ctx, nil)
	if err != nil {
		t.Fatalf("ListAssertions: %v", err)
	}
	if len(result) != 1 {
		t.Fatalf("len = %d, want 1", len(result))
	}
	if result[0].Decision != "assert" {
		t.Errorf("decision = %q", result[0].Decision)
	}
	if result[0].RelationshipType != relationships.RelProvisionsDependencyFor {
		t.Errorf("type = %q", result[0].RelationshipType)
	}
}

func TestRelationshipStoreUpsertAssertionsEmpty(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	if err := store.UpsertAssertions(ctx, nil); err != nil {
		t.Fatalf("UpsertAssertions(nil): %v", err)
	}
}

func TestRelationshipStoreListAssertionsByType(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	assertions := []relationships.Assertion{
		{
			SourceRepoID:     "repo-a",
			TargetRepoID:     "repo-b",
			RelationshipType: relationships.RelDeploysFrom,
			Decision:         "assert",
			Reason:           "deploy link",
			Actor:            "admin",
		},
		{
			SourceRepoID:     "repo-c",
			TargetRepoID:     "repo-d",
			RelationshipType: relationships.RelProvisionsDependencyFor,
			Decision:         "assert",
			Reason:           "infra link",
			Actor:            "admin",
		},
	}

	if err := store.UpsertAssertions(ctx, assertions); err != nil {
		t.Fatalf("UpsertAssertions: %v", err)
	}

	relType := relationships.RelDeploysFrom
	result, err := store.ListAssertions(ctx, &relType)
	if err != nil {
		t.Fatalf("ListAssertions: %v", err)
	}
	if len(result) != 1 {
		t.Fatalf("len = %d, want 1", len(result))
	}
	if result[0].RelationshipType != relationships.RelDeploysFrom {
		t.Errorf("type = %q", result[0].RelationshipType)
	}
}

func TestRelationshipStoreGenerationLifecycle(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	genID, err := store.CreateGeneration(ctx, "repo_deps", "run-001")
	if err != nil {
		t.Fatalf("CreateGeneration: %v", err)
	}
	if genID == "" {
		t.Fatal("genID is empty")
	}
	if !strings.HasPrefix(genID, "generation_") {
		t.Errorf("genID = %q, want generation_ prefix", genID)
	}

	if err := store.CommitGeneration(ctx, genID, "repo_deps"); err != nil {
		t.Fatalf("CommitGeneration: %v", err)
	}

	gen, ok := db.generations[genID]
	if !ok {
		t.Fatal("generation not found in db")
	}
	if gen.status != "active" {
		t.Errorf("status = %q, want active", gen.status)
	}
}

func TestRelationshipStoreUpsertAndGetResolved(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	genID, err := store.CreateGeneration(ctx, "repo_deps", "run-002")
	if err != nil {
		t.Fatalf("CreateGeneration: %v", err)
	}
	if err := store.CommitGeneration(ctx, genID, "repo_deps"); err != nil {
		t.Fatalf("CommitGeneration: %v", err)
	}

	resolved := []relationships.ResolvedRelationship{
		{
			SourceRepoID:     "repo-infra",
			TargetRepoID:     "repo-api",
			SourceEntityID:   "repo-infra",
			TargetEntityID:   "repo-api",
			RelationshipType: relationships.RelProvisionsDependencyFor,
			Confidence:       0.99,
			EvidenceCount:    3,
			Rationale:        "strong evidence",
			ResolutionSource: relationships.ResolutionSourceInferred,
			Details:          map[string]any{"evidence_kinds": []any{"TERRAFORM_APP_REPO"}},
		},
	}

	if err := store.UpsertResolved(ctx, genID, resolved); err != nil {
		t.Fatalf("UpsertResolved: %v", err)
	}

	result, err := store.GetResolvedRelationships(ctx, "repo_deps")
	if err != nil {
		t.Fatalf("GetResolvedRelationships: %v", err)
	}
	if len(result) != 1 {
		t.Fatalf("len = %d, want 1", len(result))
	}
	if result[0].Confidence != 0.99 {
		t.Errorf("confidence = %f", result[0].Confidence)
	}
	if result[0].ResolutionSource != relationships.ResolutionSourceInferred {
		t.Errorf("resolution_source = %q", result[0].ResolutionSource)
	}
}

func TestRelationshipStoreUpsertEvidenceFacts(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	genID, err := store.CreateGeneration(ctx, "repo_deps", "run-003")
	if err != nil {
		t.Fatalf("CreateGeneration: %v", err)
	}

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "repo-infra",
			TargetRepoID:     "repo-api",
			Confidence:       0.99,
			Rationale:        "app_repo match",
			Details:          map[string]any{"path": "main.tf"},
		},
	}

	if err := store.UpsertEvidenceFacts(ctx, genID, evidence); err != nil {
		t.Fatalf("UpsertEvidenceFacts: %v", err)
	}
	if len(db.evidenceFacts) != 1 {
		t.Errorf("evidence count = %d, want 1", len(db.evidenceFacts))
	}
}

func TestRelationshipStoreUpsertEvidenceFactsUsesStableContentIdentity(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	genID, err := store.CreateGeneration(ctx, "repo_deps", "run-003b")
	if err != nil {
		t.Fatalf("CreateGeneration: %v", err)
	}

	evidenceA := relationships.EvidenceFact{
		EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
		RelationshipType: relationships.RelProvisionsDependencyFor,
		SourceRepoID:     "repo-infra",
		TargetRepoID:     "repo-api",
		Confidence:       0.99,
		Rationale:        "app_repo match",
		Details:          map[string]any{"path": "main.tf"},
	}
	evidenceB := relationships.EvidenceFact{
		EvidenceKind:     relationships.EvidenceKindTerraformModuleSource,
		RelationshipType: relationships.RelUsesModule,
		SourceRepoID:     "repo-app",
		TargetRepoID:     "repo-module",
		Confidence:       0.97,
		Rationale:        "module source match",
		Details:          map[string]any{"source": "github.com/acme/repo-module"},
	}

	if err := store.UpsertEvidenceFacts(ctx, genID, []relationships.EvidenceFact{evidenceA, evidenceB}); err != nil {
		t.Fatalf("UpsertEvidenceFacts(first): %v", err)
	}
	if err := store.UpsertEvidenceFacts(ctx, genID, []relationships.EvidenceFact{evidenceB, evidenceA}); err != nil {
		t.Fatalf("UpsertEvidenceFacts(second): %v", err)
	}

	if got, want := len(db.evidenceFacts), 2; got != want {
		t.Fatalf("evidence count after reordered replay = %d, want %d", got, want)
	}
}

func TestRelationshipStoreUpsertCandidates(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	genID, err := store.CreateGeneration(ctx, "repo_deps", "run-004")
	if err != nil {
		t.Fatalf("CreateGeneration: %v", err)
	}

	candidates := []relationships.Candidate{
		{
			SourceRepoID:     "repo-infra",
			TargetRepoID:     "repo-api",
			SourceEntityID:   "repo-infra",
			TargetEntityID:   "repo-api",
			RelationshipType: relationships.RelProvisionsDependencyFor,
			Confidence:       0.99,
			EvidenceCount:    2,
			Rationale:        "aggregate",
			Details:          map[string]any{"evidence_kinds": []any{"TERRAFORM_APP_REPO"}},
		},
	}

	if err := store.UpsertCandidates(ctx, genID, candidates); err != nil {
		t.Fatalf("UpsertCandidates: %v", err)
	}
	if len(db.candidates) != 1 {
		t.Errorf("candidate count = %d, want 1", len(db.candidates))
	}
}

func TestRelationshipStoreEmptyUpserts(t *testing.T) {
	t.Parallel()

	db := newRelationshipTestDB()
	store := NewRelationshipStore(db)
	ctx := context.Background()

	if err := store.UpsertEvidenceFacts(ctx, "gen-1", nil); err != nil {
		t.Errorf("UpsertEvidenceFacts(nil): %v", err)
	}
	if err := store.UpsertCandidates(ctx, "gen-1", nil); err != nil {
		t.Errorf("UpsertCandidates(nil): %v", err)
	}
	if err := store.UpsertResolved(ctx, "gen-1", nil); err != nil {
		t.Errorf("UpsertResolved(nil): %v", err)
	}
}

func TestRelationshipSchemaSQL(t *testing.T) {
	t.Parallel()

	schema := RelationshipSchemaSQL()
	for _, table := range []string{
		"relationship_assertions",
		"relationship_generations",
		"relationship_evidence_facts",
		"relationship_candidates",
		"resolved_relationships",
	} {
		if !strings.Contains(schema, table) {
			t.Errorf("missing table %q in schema", table)
		}
	}
}

// -- test helpers --

type generationRecord struct {
	scope       string
	runID       string
	status      string
	activatedAt *time.Time
}

type evidenceRecord struct {
	generationID   string
	evidenceKind   string
	relType        string
	sourceRepoID   string
	targetRepoID   string
	sourceEntityID string
	targetEntityID string
	confidence     float64
	rationale      string
	details        map[string]any
}

type candidateRecord struct {
	generationID   string
	sourceRepoID   string
	targetRepoID   string
	sourceEntityID string
	targetEntityID string
	relType        string
	confidence     float64
	evidenceCount  int
	rationale      string
	details        map[string]any
}

type resolvedRecord struct {
	generationID     string
	sourceRepoID     string
	targetRepoID     string
	sourceEntityID   string
	targetEntityID   string
	relType          string
	confidence       float64
	evidenceCount    int
	rationale        string
	resolutionSource string
	details          map[string]any
}

type assertionRecord struct {
	sourceRepoID   string
	targetRepoID   string
	sourceEntityID string
	targetEntityID string
	relType        string
	decision       string
	reason         string
	actor          string
	updatedAt      time.Time
}

// relationshipTestDB is an in-memory mock of ExecQueryer for relationship
// store unit testing.
type relationshipTestDB struct {
	assertions    map[string]assertionRecord
	generations   map[string]generationRecord
	evidenceFacts map[string]evidenceRecord
	candidates    map[string]candidateRecord
	resolved      map[string]resolvedRecord
}

func newRelationshipTestDB() *relationshipTestDB {
	return &relationshipTestDB{
		assertions:    make(map[string]assertionRecord),
		generations:   make(map[string]generationRecord),
		evidenceFacts: make(map[string]evidenceRecord),
		candidates:    make(map[string]candidateRecord),
		resolved:      make(map[string]resolvedRecord),
	}
}

func (db *relationshipTestDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	switch {
	case strings.Contains(query, "INSERT INTO relationship_assertions"):
		now := args[9].(time.Time)
		srcEntity := nullableToString(args[3])
		tgtEntity := nullableToString(args[4])
		db.assertions[args[0].(string)] = assertionRecord{
			sourceRepoID:   args[1].(string),
			targetRepoID:   args[2].(string),
			sourceEntityID: srcEntity,
			targetEntityID: tgtEntity,
			relType:        args[5].(string),
			decision:       args[6].(string),
			reason:         args[7].(string),
			actor:          args[8].(string),
			updatedAt:      now,
		}
		return proofResult{}, nil

	case strings.Contains(query, "INSERT INTO relationship_generations"):
		runID := ""
		if args[2] != nil {
			runID = args[2].(string)
		}
		db.generations[args[0].(string)] = generationRecord{
			scope:  args[1].(string),
			runID:  runID,
			status: "pending",
		}
		return proofResult{}, nil

	case strings.Contains(query, "UPDATE relationship_generations"):
		genID := args[1].(string)
		if gen, ok := db.generations[genID]; ok {
			now := args[0].(time.Time)
			gen.status = "active"
			gen.activatedAt = &now
			db.generations[genID] = gen
		}
		return proofResult{}, nil

	case strings.Contains(query, "INSERT INTO relationship_evidence_facts"):
		details := parseJSONBytes(args[10])
		db.evidenceFacts[args[0].(string)] = evidenceRecord{
			generationID:   args[1].(string),
			evidenceKind:   args[2].(string),
			relType:        args[3].(string),
			sourceRepoID:   nullableToString(args[4]),
			targetRepoID:   nullableToString(args[5]),
			sourceEntityID: nullableToString(args[6]),
			targetEntityID: nullableToString(args[7]),
			confidence:     args[8].(float64),
			rationale:      args[9].(string),
			details:        details,
		}
		return proofResult{}, nil

	case strings.Contains(query, "INSERT INTO relationship_candidates"):
		details := parseJSONBytes(args[10])
		db.candidates[args[0].(string)] = candidateRecord{
			generationID:   args[1].(string),
			sourceRepoID:   nullableToString(args[2]),
			targetRepoID:   nullableToString(args[3]),
			sourceEntityID: nullableToString(args[4]),
			targetEntityID: nullableToString(args[5]),
			relType:        args[6].(string),
			confidence:     args[7].(float64),
			evidenceCount:  args[8].(int),
			rationale:      args[9].(string),
			details:        details,
		}
		return proofResult{}, nil

	case strings.Contains(query, "INSERT INTO resolved_relationships"):
		details := parseJSONBytes(args[11])
		db.resolved[args[0].(string)] = resolvedRecord{
			generationID:     args[1].(string),
			sourceRepoID:     nullableToString(args[2]),
			targetRepoID:     nullableToString(args[3]),
			sourceEntityID:   nullableToString(args[4]),
			targetEntityID:   nullableToString(args[5]),
			relType:          args[6].(string),
			confidence:       args[7].(float64),
			evidenceCount:    args[8].(int),
			rationale:        args[9].(string),
			resolutionSource: args[10].(string),
			details:          details,
		}
		return proofResult{}, nil

	default:
		return nil, fmt.Errorf("unexpected exec query: %s", query)
	}
}

func (db *relationshipTestDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	switch {
	case strings.Contains(query, "FROM relationship_assertions") && strings.Contains(query, "WHERE relationship_type"):
		relType := args[0].(string)
		return db.queryAssertions(func(a assertionRecord) bool {
			return a.relType == relType
		}), nil

	case strings.Contains(query, "FROM relationship_assertions"):
		return db.queryAssertions(func(_ assertionRecord) bool { return true }), nil

	case strings.Contains(query, "FROM resolved_relationships"):
		scopeID := args[0].(string)
		return db.queryResolved(scopeID), nil

	default:
		return nil, fmt.Errorf("unexpected query: %s", query)
	}
}

func (db *relationshipTestDB) queryAssertions(filter func(assertionRecord) bool) *relationshipRows {
	var rows [][]any
	// Sort by updatedAt for deterministic ordering.
	type kv struct {
		key string
		val assertionRecord
	}
	sorted := make([]kv, 0, len(db.assertions))
	for k, v := range db.assertions {
		sorted = append(sorted, kv{k, v})
	}
	sort.Slice(sorted, func(i, j int) bool {
		return sorted[i].val.updatedAt.Before(sorted[j].val.updatedAt)
	})
	for _, item := range sorted {
		a := item.val
		if !filter(a) {
			continue
		}
		srcEntity := a.sourceEntityID
		if srcEntity == "" {
			srcEntity = a.sourceRepoID
		}
		tgtEntity := a.targetEntityID
		if tgtEntity == "" {
			tgtEntity = a.targetRepoID
		}
		rows = append(rows, []any{
			a.sourceRepoID, a.targetRepoID,
			srcEntity, tgtEntity,
			a.relType, a.decision, a.reason, a.actor,
		})
	}
	return newRelationshipRows(rows)
}

func (db *relationshipTestDB) queryResolved(scopeID string) *relationshipRows {
	// Find active generation for scope.
	var activeGenID string
	for genID, gen := range db.generations {
		if gen.scope == scopeID && gen.status == "active" {
			activeGenID = genID
			break
		}
	}
	if activeGenID == "" {
		return newRelationshipRows(nil)
	}

	var rows [][]any
	type kv struct {
		key string
		val resolvedRecord
	}
	sorted := make([]kv, 0, len(db.resolved))
	for k, v := range db.resolved {
		sorted = append(sorted, kv{k, v})
	}
	sort.Slice(sorted, func(i, j int) bool {
		return sorted[i].key < sorted[j].key
	})
	for _, item := range sorted {
		r := item.val
		if r.generationID != activeGenID {
			continue
		}
		srcEntity := r.sourceEntityID
		if srcEntity == "" {
			srcEntity = r.sourceRepoID
		}
		tgtEntity := r.targetEntityID
		if tgtEntity == "" {
			tgtEntity = r.targetRepoID
		}
		detailsBytes, _ := json.Marshal(r.details)
		rows = append(rows, []any{
			r.sourceRepoID, r.targetRepoID,
			srcEntity, tgtEntity,
			r.relType, r.confidence, r.evidenceCount,
			r.rationale, r.resolutionSource, detailsBytes,
		})
	}
	return newRelationshipRows(rows)
}

func nullableToString(v any) string {
	if v == nil {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return s
}

func parseJSONBytes(v any) map[string]any {
	b, ok := v.([]byte)
	if !ok {
		return nil
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return nil
	}
	return m
}

// relationshipRows implements the Rows interface for relationship test queries.
type relationshipRows struct {
	data [][]any
	idx  int
}

func newRelationshipRows(data [][]any) *relationshipRows {
	return &relationshipRows{data: data, idx: -1}
}

func (r *relationshipRows) Next() bool {
	r.idx++
	return r.idx < len(r.data)
}

func (r *relationshipRows) Scan(dest ...any) error {
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
		case *float64:
			*d = val.(float64)
		case *int:
			*d = val.(int)
		case *time.Time:
			*d = val.(time.Time)
		case *[]byte:
			if b, ok := val.([]byte); ok {
				*d = b
			}
		case *sql.NullString:
			if val == nil {
				d.Valid = false
			} else {
				d.String = val.(string)
				d.Valid = true
			}
		default:
			return fmt.Errorf("unsupported scan dest type %T", dest[i])
		}
	}
	return nil
}

func (r *relationshipRows) Err() error   { return nil }
func (r *relationshipRows) Close() error { return nil }
