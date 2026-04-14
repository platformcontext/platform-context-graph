package postgres

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestIngestionStoreCommitScopeGenerationPersistsProjectionInput(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC)
	db := &fakeTransactionalDB{tx: &fakeTx{}}
	store := NewIngestionStore(db)
	store.Now = func() time.Time { return now }

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
		Metadata: map[string]string{
			"repo_id": "repo-123",
		},
	}
	generation := scope.ScopeGeneration{
		GenerationID: "generation-456",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 59, 0, 0, time.UTC),
		IngestedAt:   now,
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}
	envelopes := []facts.Envelope{{
		FactID:        "fact-1",
		ScopeID:       "scope-123",
		GenerationID:  "generation-456",
		FactKind:      "repository",
		StableFactKey: "repository:repo-123",
		ObservedAt:    generation.ObservedAt,
		Payload:       map[string]any{"graph_id": "repo-123"},
		SourceRef: facts.Ref{
			SourceSystem: "git",
			FactKey:      "fact-key",
		},
	}}

	if err := store.CommitScopeGeneration(context.Background(), scopeValue, generation, testFactChannel(envelopes)); err != nil {
		t.Fatalf("CommitScopeGeneration() error = %v, want nil", err)
	}

	if got, want := db.beginCalls, 1; got != want {
		t.Fatalf("begin call count = %d, want %d", got, want)
	}
	if !db.tx.committed {
		t.Fatal("transaction committed = false, want true")
	}
	if db.tx.rolledBack {
		t.Fatal("transaction rolledBack = true, want false")
	}
	if got, want := len(db.tx.execs), 4; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	for index, want := range []string{
		"INSERT INTO ingestion_scopes",
		"INSERT INTO scope_generations",
		"INSERT INTO fact_records",
		"INSERT INTO fact_work_items",
	} {
		if !strings.Contains(db.tx.execs[index].query, want) {
			t.Fatalf("exec[%d] query = %q, want substring %q", index, db.tx.execs[index].query, want)
		}
	}
	if got, want := db.tx.execs[3].args[3], "source_local"; got != want {
		t.Fatalf("projector domain arg = %v, want %v", got, want)
	}
}

func TestIngestionStoreCommitScopeGenerationRollsBackOnProjectorEnqueueFailure(t *testing.T) {
	t.Parallel()

	db := &fakeTransactionalDB{
		tx: &fakeTx{
			execErrors: map[int]error{
				2: errors.New("insert projector work failed"),
			},
		},
	}
	store := NewIngestionStore(db)

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
	}
	generation := scope.ScopeGeneration{
		GenerationID: "generation-456",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 59, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}

	err := store.CommitScopeGeneration(context.Background(), scopeValue, generation, nil)
	if err == nil {
		t.Fatal("CommitScopeGeneration() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "enqueue projector work") {
		t.Fatalf("CommitScopeGeneration() error = %q, want enqueue projector work context", err)
	}
	if db.tx.committed {
		t.Fatal("transaction committed = true, want false")
	}
	if !db.tx.rolledBack {
		t.Fatal("transaction rolledBack = false, want true")
	}
}

func TestUpsertIngestionScopeQueryPreservesActiveStatusDuringPendingRefresh(t *testing.T) {
	t.Parallel()

	for _, want := range []string{
		"ingestion_scopes.active_generation_id IS NOT NULL",
		"EXCLUDED.active_generation_id IS NULL",
		"EXCLUDED.status = 'pending'",
		"THEN ingestion_scopes.status",
	} {
		if !strings.Contains(upsertIngestionScopeQuery, want) {
			t.Fatalf("upsertIngestionScopeQuery missing %q", want)
		}
	}
}

func TestIngestionStoreCommitScopeGenerationSkipsUnchangedActiveGeneration(t *testing.T) {
	telemetry.ResetSkippedRefreshCountForTesting()
	t.Cleanup(telemetry.ResetSkippedRefreshCountForTesting)

	now := time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC)
	db := &fakeTransactionalDB{
		tx: &fakeTx{},
		queryResponses: []queueFakeRows{{
			rows: [][]any{{"generation-active", "fingerprint-same"}},
		}},
	}
	store := NewIngestionStore(db)
	store.Now = func() time.Time { return now }

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
	}
	generation := scope.ScopeGeneration{
		GenerationID:  "generation-456",
		ScopeID:       "scope-123",
		ObservedAt:    time.Date(2026, time.April, 12, 11, 59, 0, 0, time.UTC),
		IngestedAt:    now,
		Status:        scope.GenerationStatusPending,
		TriggerKind:   scope.TriggerKindSnapshot,
		FreshnessHint: "fingerprint-same",
	}

	if err := store.CommitScopeGeneration(context.Background(), scopeValue, generation, nil); err != nil {
		t.Fatalf("CommitScopeGeneration() error = %v, want nil", err)
	}

	if got, want := len(db.queries), 1; got != want {
		t.Fatalf("query count = %d, want %d", got, want)
	}
	if got, want := db.beginCalls, 0; got != want {
		t.Fatalf("begin call count = %d, want %d", got, want)
	}
	if got, want := len(db.tx.execs), 0; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if got, want := telemetry.SkippedRefreshCount(), uint64(1); got != want {
		t.Fatalf("SkippedRefreshCount() = %d, want %d", got, want)
	}
}

func TestIngestionStoreCommitScopeGenerationContinuesWhenActiveFingerprintDiffers(t *testing.T) {
	telemetry.ResetSkippedRefreshCountForTesting()
	t.Cleanup(telemetry.ResetSkippedRefreshCountForTesting)

	now := time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC)
	db := &fakeTransactionalDB{
		tx: &fakeTx{},
		queryResponses: []queueFakeRows{{
			rows: [][]any{{"generation-active", "fingerprint-old"}},
		}},
	}
	store := NewIngestionStore(db)
	store.Now = func() time.Time { return now }

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
	}
	generation := scope.ScopeGeneration{
		GenerationID:  "generation-456",
		ScopeID:       "scope-123",
		ObservedAt:    time.Date(2026, time.April, 12, 11, 59, 0, 0, time.UTC),
		IngestedAt:    now,
		Status:        scope.GenerationStatusPending,
		TriggerKind:   scope.TriggerKindSnapshot,
		FreshnessHint: "fingerprint-new",
	}

	if err := store.CommitScopeGeneration(context.Background(), scopeValue, generation, nil); err != nil {
		t.Fatalf("CommitScopeGeneration() error = %v, want nil", err)
	}

	if got, want := len(db.queries), 1; got != want {
		t.Fatalf("query count = %d, want %d", got, want)
	}
	if got, want := db.beginCalls, 1; got != want {
		t.Fatalf("begin call count = %d, want %d", got, want)
	}
	if got, want := len(db.tx.execs), 3; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if got, want := telemetry.SkippedRefreshCount(), uint64(0); got != want {
		t.Fatalf("SkippedRefreshCount() = %d, want %d", got, want)
	}
}

type fakeTransactionalDB struct {
	tx             *fakeTx
	beginCalls     int
	beginErr       error
	queries        []fakeQueryCall
	queryResponses []queueFakeRows
}

func (f *fakeTransactionalDB) Begin(context.Context) (Transaction, error) {
	f.beginCalls++
	if f.beginErr != nil {
		return nil, f.beginErr
	}
	return f.tx, nil
}

func (f *fakeTransactionalDB) ExecContext(context.Context, string, ...any) (sql.Result, error) {
	return nil, errors.New("unexpected ExecContext on outer db")
}

func (f *fakeTransactionalDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	f.queries = append(f.queries, fakeQueryCall{query: query, args: args})
	if len(f.queryResponses) == 0 {
		return nil, errors.New("unexpected QueryContext on outer db")
	}

	rows := f.queryResponses[0]
	f.queryResponses = f.queryResponses[1:]
	if rows.err != nil {
		return nil, rows.err
	}

	return &rows, nil
}

type fakeTx struct {
	execs      []fakeExecCall
	queries    []fakeQueryCall
	execErrors map[int]error
	committed  bool
	rolledBack bool
}

func (f *fakeTx) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	callIndex := len(f.execs)
	f.execs = append(f.execs, fakeExecCall{query: query, args: args})
	if err := f.execErrors[callIndex]; err != nil {
		return nil, err
	}
	return fakeResult{}, nil
}

func (f *fakeTx) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	f.queries = append(f.queries, fakeQueryCall{query: query, args: args})
	return nil, errors.New("unexpected query in transaction")
}

func (f *fakeTx) Commit() error {
	f.committed = true
	return nil
}

func (f *fakeTx) Rollback() error {
	f.rolledBack = true
	return nil
}
