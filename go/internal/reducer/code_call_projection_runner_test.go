package reducer

import (
	"context"
	"errors"
	"sort"
	"sync"
	"testing"
	"time"
)

func TestCodeCallProjectionRunnerConfigDefaults(t *testing.T) {
	t.Parallel()

	cfg := CodeCallProjectionRunnerConfig{}
	if got := cfg.pollInterval(); got != defaultSharedPollInterval {
		t.Fatalf("pollInterval() = %v, want %v", got, defaultSharedPollInterval)
	}
	if got := cfg.leaseTTL(); got != defaultLeaseTTL {
		t.Fatalf("leaseTTL() = %v, want %v", got, defaultLeaseTTL)
	}
	if got := cfg.batchLimit(); got != defaultBatchLimit {
		t.Fatalf("batchLimit() = %d, want %d", got, defaultBatchLimit)
	}
	if got := cfg.leaseOwner(); got != defaultCodeCallLeaseOwner {
		t.Fatalf("leaseOwner() = %q, want %q", got, defaultCodeCallLeaseOwner)
	}
}

func TestCodeCallProjectionRunnerValidation(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		runner CodeCallProjectionRunner
	}{
		{
			name:   "missing intent reader",
			runner: CodeCallProjectionRunner{LeaseManager: &fakeCodeCallIntentStore{leaseGranted: true}, EdgeWriter: &recordingCodeCallProjectionEdgeWriter{}, AcceptedGen: func(SharedProjectionAcceptanceKey) (string, bool) { return "", false }},
		},
		{
			name:   "missing lease manager",
			runner: CodeCallProjectionRunner{IntentReader: &fakeCodeCallIntentStore{leaseGranted: true}, EdgeWriter: &recordingCodeCallProjectionEdgeWriter{}, AcceptedGen: func(SharedProjectionAcceptanceKey) (string, bool) { return "", false }},
		},
		{
			name:   "missing edge writer",
			runner: CodeCallProjectionRunner{IntentReader: &fakeCodeCallIntentStore{leaseGranted: true}, LeaseManager: &fakeCodeCallIntentStore{leaseGranted: true}, AcceptedGen: func(SharedProjectionAcceptanceKey) (string, bool) { return "", false }},
		},
		{
			name:   "missing accepted generation lookup",
			runner: CodeCallProjectionRunner{IntentReader: &fakeCodeCallIntentStore{leaseGranted: true}, LeaseManager: &fakeCodeCallIntentStore{leaseGranted: true}, EdgeWriter: &recordingCodeCallProjectionEdgeWriter{}},
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			if err := tt.runner.validate(); err == nil {
				t.Fatal("validate() error = nil, want non-nil")
			}
		})
	}
}

func TestCodeCallProjectionRunnerProcessesRepoAtomically(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 16, 12, 0, 0, 0, time.UTC)
	reader := &fakeCodeCallIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			{
				IntentID:         "refresh-1",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "repo:repo-a",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{"action": "refresh"},
				CreatedAt:        now,
			},
			{
				IntentID:         "edge-1",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "caller->callee",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload: map[string]any{
					"repo_id":          "repo-a",
					"caller_entity_id": "caller",
					"callee_entity_id": "callee",
					"evidence_source":  codeCallEvidenceSource,
				},
				CreatedAt: now.Add(time.Second),
			},
			{
				IntentID:         "meta-1",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "child->meta",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload: map[string]any{
					"repo_id":           "repo-a",
					"source_entity_id":  "child",
					"target_entity_id":  "meta",
					"relationship_type": "USES_METACLASS",
					"evidence_source":   pythonMetaclassEvidenceSource,
				},
				CreatedAt: now.Add(2 * time.Second),
			},
			{
				IntentID:         "stale-1",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "stale",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-old",
				Payload:          map[string]any{"action": "refresh"},
				CreatedAt:        now.Add(-time.Second),
			},
		},
		pendingByAcceptance: map[string][]SharedProjectionIntentRow{
			"scope-a|repo-a|run-1": {
				{
					IntentID:         "stale-1",
					ProjectionDomain: DomainCodeCalls,
					PartitionKey:     "stale",
					ScopeID:          "scope-a",
					AcceptanceUnitID: "repo-a",
					RepositoryID:     "repo-a",
					SourceRunID:      "run-1",
					GenerationID:     "gen-old",
					Payload:          map[string]any{"action": "refresh"},
					CreatedAt:        now.Add(-time.Second),
				},
				{
					IntentID:         "refresh-1",
					ProjectionDomain: DomainCodeCalls,
					PartitionKey:     "repo:repo-a",
					ScopeID:          "scope-a",
					AcceptanceUnitID: "repo-a",
					RepositoryID:     "repo-a",
					SourceRunID:      "run-1",
					GenerationID:     "gen-1",
					Payload:          map[string]any{"action": "refresh"},
					CreatedAt:        now,
				},
				{
					IntentID:         "edge-1",
					ProjectionDomain: DomainCodeCalls,
					PartitionKey:     "caller->callee",
					ScopeID:          "scope-a",
					AcceptanceUnitID: "repo-a",
					RepositoryID:     "repo-a",
					SourceRunID:      "run-1",
					GenerationID:     "gen-1",
					Payload: map[string]any{
						"repo_id":          "repo-a",
						"caller_entity_id": "caller",
						"callee_entity_id": "callee",
						"evidence_source":  codeCallEvidenceSource,
					},
					CreatedAt: now.Add(time.Second),
				},
				{
					IntentID:         "meta-1",
					ProjectionDomain: DomainCodeCalls,
					PartitionKey:     "child->meta",
					ScopeID:          "scope-a",
					AcceptanceUnitID: "repo-a",
					RepositoryID:     "repo-a",
					SourceRunID:      "run-1",
					GenerationID:     "gen-1",
					Payload: map[string]any{
						"repo_id":           "repo-a",
						"source_entity_id":  "child",
						"target_entity_id":  "meta",
						"relationship_type": "USES_METACLASS",
						"evidence_source":   pythonMetaclassEvidenceSource,
					},
					CreatedAt: now.Add(2 * time.Second),
				},
			},
		},
		leaseGranted: true,
	}
	writer := &recordingCodeCallProjectionEdgeWriter{}
	runner := CodeCallProjectionRunner{
		IntentReader: reader,
		LeaseManager: reader,
		EdgeWriter:   writer,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			return "gen-1", key.ScopeID == "scope-a" && key.AcceptanceUnitID == "repo-a" && key.SourceRunID == "run-1"
		},
		Config: CodeCallProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
	}

	result, err := runner.processOnce(context.Background(), now)
	if err != nil {
		t.Fatalf("processOnce() error = %v", err)
	}
	if !result.LeaseAcquired {
		t.Fatal("LeaseAcquired = false, want true")
	}
	if result.ProcessedIntents != 4 {
		t.Fatalf("ProcessedIntents = %d, want 4", result.ProcessedIntents)
	}
	if len(writer.retractCalls) != 2 {
		t.Fatalf("len(retractCalls) = %d, want 2 evidence-source retracts", len(writer.retractCalls))
	}
	if got, want := writer.retractCalls[0].evidenceSource, codeCallEvidenceSource; got != want {
		t.Fatalf("retractCalls[0].evidenceSource = %q, want %q", got, want)
	}
	if got, want := writer.retractCalls[1].evidenceSource, pythonMetaclassEvidenceSource; got != want {
		t.Fatalf("retractCalls[1].evidenceSource = %q, want %q", got, want)
	}
	if len(writer.writeCalls) != 2 {
		t.Fatalf("len(writeCalls) = %d, want 2 evidence-grouped writes", len(writer.writeCalls))
	}
	if len(reader.marked) != 4 {
		t.Fatalf("len(marked) = %d, want 4", len(reader.marked))
	}
}

func TestCodeCallProjectionRunnerRunContinuesAfterCycleError(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 17, 9, 0, 0, 0, time.UTC)
	reader := &fakeCodeCallIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			{
				IntentID:         "edge-1",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "caller->callee",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload: map[string]any{
					"repo_id":          "repo-a",
					"caller_entity_id": "caller",
					"callee_entity_id": "callee",
					"evidence_source":  codeCallEvidenceSource,
				},
				CreatedAt: now,
			},
		},
		pendingByAcceptance: map[string][]SharedProjectionIntentRow{
			"scope-a|repo-a|run-1": {
				{
					IntentID:         "edge-1",
					ProjectionDomain: DomainCodeCalls,
					PartitionKey:     "caller->callee",
					ScopeID:          "scope-a",
					AcceptanceUnitID: "repo-a",
					RepositoryID:     "repo-a",
					SourceRunID:      "run-1",
					GenerationID:     "gen-1",
					Payload: map[string]any{
						"repo_id":          "repo-a",
						"caller_entity_id": "caller",
						"callee_entity_id": "callee",
						"evidence_source":  codeCallEvidenceSource,
					},
					CreatedAt: now,
				},
			},
		},
		leaseGranted: true,
	}
	writer := &flakyCodeCallProjectionEdgeWriter{
		err:             errors.New("neo4j transient write conflict"),
		retractFailures: 1,
	}

	waits := make([]time.Duration, 0, 2)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	runner := CodeCallProjectionRunner{
		IntentReader: reader,
		LeaseManager: reader,
		EdgeWriter:   writer,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			return "gen-1", key.ScopeID == "scope-a" && key.AcceptanceUnitID == "repo-a" && key.SourceRunID == "run-1"
		},
		Config: CodeCallProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
		Wait: func(_ context.Context, interval time.Duration) error {
			waits = append(waits, interval)
			if len(waits) == 1 {
				return nil
			}
			cancel()
			return context.Canceled
		},
	}

	if err := runner.Run(ctx); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}
	if got := len(reader.marked); got != 1 {
		t.Fatalf("len(marked) = %d, want 1 completed intent after retry", got)
	}
	if got := len(writer.writeCalls); got != 1 {
		t.Fatalf("len(writeCalls) = %d, want 1 successful write call", got)
	}
	if got := len(waits); got != 2 {
		t.Fatalf("len(waits) = %d, want 2 waits (post-error backoff, then idle poll)", got)
	}
	if got, want := waits[0], 10*time.Millisecond; got != want {
		t.Fatalf("waits[0] = %v, want %v", got, want)
	}
	if got, want := waits[1], 10*time.Millisecond; got != want {
		t.Fatalf("waits[1] = %v, want %v", got, want)
	}
}

func TestCodeCallProjectionRunnerLoadAllAcceptanceUnitIntentsRejectsOversizedSlice(t *testing.T) {
	t.Parallel()

	reader := &fakeCodeCallIntentStore{
		acceptanceResponder: func(_ SharedProjectionAcceptanceKey, limit int) ([]SharedProjectionIntentRow, error) {
			rows := make([]SharedProjectionIntentRow, limit)
			for i := range rows {
				rows[i] = SharedProjectionIntentRow{
					IntentID:         "intent",
					ProjectionDomain: DomainCodeCalls,
					ScopeID:          "scope-a",
					AcceptanceUnitID: "repo-a",
					RepositoryID:     "repo-a",
					SourceRunID:      "run-1",
					GenerationID:     "gen-1",
				}
			}
			return rows, nil
		},
	}
	runner := CodeCallProjectionRunner{
		IntentReader: reader,
		Config:       CodeCallProjectionRunnerConfig{BatchLimit: 100},
	}

	_, err := runner.loadAllAcceptanceUnitIntents(context.Background(), SharedProjectionAcceptanceKey{
		ScopeID:          "scope-a",
		AcceptanceUnitID: "repo-a",
		SourceRunID:      "run-1",
	})
	if err == nil {
		t.Fatal("loadAllAcceptanceUnitIntents() error = nil, want non-nil")
	}
	if got, want := reader.acceptanceLimitRequests[len(reader.acceptanceLimitRequests)-1], maxCodeCallAcceptanceScanLimit; got != want {
		t.Fatalf("final acceptance scan limit = %d, want cap %d", got, want)
	}
	if len(reader.acceptanceLimitRequests) < 2 {
		t.Fatalf("acceptanceLimitRequests = %v, want growth up to cap", reader.acceptanceLimitRequests)
	}
}

func TestCodeCallProjectionRunnerSelectsAcceptanceUnitUsingScopeAndUnit(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 17, 10, 0, 0, 0, time.UTC)
	reader := &fakeCodeCallIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			{
				IntentID:         "scope-b",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "caller->callee",
				ScopeID:          "scope-b",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-b",
				CreatedAt:        now,
			},
			{
				IntentID:         "scope-a",
				ProjectionDomain: DomainCodeCalls,
				PartitionKey:     "caller->callee",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-a",
				CreatedAt:        now.Add(time.Second),
			},
		},
	}
	runner := CodeCallProjectionRunner{
		IntentReader: reader,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			if key.ScopeID == "scope-a" && key.AcceptanceUnitID == "repo-a" && key.SourceRunID == "run-1" {
				return "gen-a", true
			}
			return "", false
		},
		Config: CodeCallProjectionRunnerConfig{BatchLimit: 10},
	}

	key, err := runner.selectAcceptanceUnitWork(context.Background())
	if err != nil {
		t.Fatalf("selectAcceptanceUnitWork() error = %v", err)
	}
	if got, want := key.ScopeID, "scope-a"; got != want {
		t.Fatalf("key.ScopeID = %q, want %q", got, want)
	}
	if got, want := key.AcceptanceUnitID, "repo-a"; got != want {
		t.Fatalf("key.AcceptanceUnitID = %q, want %q", got, want)
	}
	if got, want := key.SourceRunID, "run-1"; got != want {
		t.Fatalf("key.SourceRunID = %q, want %q", got, want)
	}
}

type fakeCodeCallIntentStore struct {
	mu                      sync.Mutex
	pendingByDomain         []SharedProjectionIntentRow
	pendingByAcceptance     map[string][]SharedProjectionIntentRow
	marked                  []string
	leaseGranted            bool
	claims                  int
	acceptanceLimitRequests []int
	acceptanceResponder     func(key SharedProjectionAcceptanceKey, limit int) ([]SharedProjectionIntentRow, error)
}

func (f *fakeCodeCallIntentStore) ListPendingDomainIntents(_ context.Context, _ string, limit int) ([]SharedProjectionIntentRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	rows := make([]SharedProjectionIntentRow, 0, len(f.pendingByDomain))
	for _, row := range f.pendingByDomain {
		if row.CompletedAt != nil {
			continue
		}
		rows = append(rows, row)
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if !rows[i].CreatedAt.Equal(rows[j].CreatedAt) {
			return rows[i].CreatedAt.Before(rows[j].CreatedAt)
		}
		return rows[i].IntentID < rows[j].IntentID
	})
	if limit > 0 && len(rows) > limit {
		rows = rows[:limit]
	}
	return rows, nil
}

func (f *fakeCodeCallIntentStore) ListPendingAcceptanceUnitIntents(_ context.Context, key SharedProjectionAcceptanceKey, _ string, limit int) ([]SharedProjectionIntentRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	f.acceptanceLimitRequests = append(f.acceptanceLimitRequests, limit)
	if f.acceptanceResponder != nil {
		return f.acceptanceResponder(key, limit)
	}

	rows := make([]SharedProjectionIntentRow, 0, len(f.pendingByAcceptance[key.ScopeID+"|"+key.AcceptanceUnitID+"|"+key.SourceRunID]))
	for _, row := range f.pendingByAcceptance[key.ScopeID+"|"+key.AcceptanceUnitID+"|"+key.SourceRunID] {
		if row.CompletedAt != nil {
			continue
		}
		rows = append(rows, row)
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if !rows[i].CreatedAt.Equal(rows[j].CreatedAt) {
			return rows[i].CreatedAt.Before(rows[j].CreatedAt)
		}
		return rows[i].IntentID < rows[j].IntentID
	})
	if limit > 0 && len(rows) > limit {
		rows = rows[:limit]
	}
	return rows, nil
}

func (f *fakeCodeCallIntentStore) MarkIntentsCompleted(_ context.Context, intentIDs []string, _ time.Time) error {
	f.mu.Lock()
	defer f.mu.Unlock()

	f.marked = append(f.marked, intentIDs...)
	completedAt := time.Now().UTC()
	markSet := make(map[string]struct{}, len(intentIDs))
	for _, intentID := range intentIDs {
		markSet[intentID] = struct{}{}
	}
	for i := range f.pendingByDomain {
		if _, ok := markSet[f.pendingByDomain[i].IntentID]; ok {
			f.pendingByDomain[i].CompletedAt = &completedAt
		}
	}
	for key := range f.pendingByAcceptance {
		for i := range f.pendingByAcceptance[key] {
			if _, ok := markSet[f.pendingByAcceptance[key][i].IntentID]; ok {
				f.pendingByAcceptance[key][i].CompletedAt = &completedAt
			}
		}
	}
	return nil
}

func (f *fakeCodeCallIntentStore) ClaimPartitionLease(_ context.Context, _ string, _, _ int, _ string, _ time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	f.claims++
	return f.leaseGranted, nil
}

func (f *fakeCodeCallIntentStore) ReleasePartitionLease(_ context.Context, _ string, _, _ int, _ string) error {
	return nil
}

type recordingCodeCallProjectionEdgeWriter struct {
	retractCalls []recordedProjectionCall
	writeCalls   []recordedProjectionCall
}

type recordedProjectionCall struct {
	rows           []SharedProjectionIntentRow
	evidenceSource string
}

func (r *recordingCodeCallProjectionEdgeWriter) RetractEdges(_ context.Context, _ string, rows []SharedProjectionIntentRow, evidenceSource string) error {
	r.retractCalls = append(r.retractCalls, recordedProjectionCall{
		rows:           append([]SharedProjectionIntentRow(nil), rows...),
		evidenceSource: evidenceSource,
	})
	return nil
}

func (r *recordingCodeCallProjectionEdgeWriter) WriteEdges(_ context.Context, _ string, rows []SharedProjectionIntentRow, evidenceSource string) error {
	r.writeCalls = append(r.writeCalls, recordedProjectionCall{
		rows:           append([]SharedProjectionIntentRow(nil), rows...),
		evidenceSource: evidenceSource,
	})
	return nil
}

type flakyCodeCallProjectionEdgeWriter struct {
	recordingCodeCallProjectionEdgeWriter
	err             error
	retractFailures int
	writeFailures   int
}

func (r *flakyCodeCallProjectionEdgeWriter) RetractEdges(ctx context.Context, domain string, rows []SharedProjectionIntentRow, evidenceSource string) error {
	if r.retractFailures > 0 {
		r.retractFailures--
		return r.err
	}
	return r.recordingCodeCallProjectionEdgeWriter.RetractEdges(ctx, domain, rows, evidenceSource)
}

func (r *flakyCodeCallProjectionEdgeWriter) WriteEdges(ctx context.Context, domain string, rows []SharedProjectionIntentRow, evidenceSource string) error {
	if r.writeFailures > 0 {
		r.writeFailures--
		return r.err
	}
	return r.recordingCodeCallProjectionEdgeWriter.WriteEdges(ctx, domain, rows, evidenceSource)
}
