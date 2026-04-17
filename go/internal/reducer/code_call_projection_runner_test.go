package reducer

import (
	"context"
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
			runner: CodeCallProjectionRunner{LeaseManager: &fakeCodeCallIntentStore{leaseGranted: true}, EdgeWriter: &recordingCodeCallProjectionEdgeWriter{}, AcceptedGen: func(_, _ string) (string, bool) { return "", false }},
		},
		{
			name:   "missing lease manager",
			runner: CodeCallProjectionRunner{IntentReader: &fakeCodeCallIntentStore{leaseGranted: true}, EdgeWriter: &recordingCodeCallProjectionEdgeWriter{}, AcceptedGen: func(_, _ string) (string, bool) { return "", false }},
		},
		{
			name:   "missing edge writer",
			runner: CodeCallProjectionRunner{IntentReader: &fakeCodeCallIntentStore{leaseGranted: true}, LeaseManager: &fakeCodeCallIntentStore{leaseGranted: true}, AcceptedGen: func(_, _ string) (string, bool) { return "", false }},
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
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-old",
				Payload:          map[string]any{"action": "refresh"},
				CreatedAt:        now.Add(-time.Second),
			},
		},
		pendingByRepoRun: map[string][]SharedProjectionIntentRow{
			"repo-a|run-1": {
				{
					IntentID:         "stale-1",
					ProjectionDomain: DomainCodeCalls,
					PartitionKey:     "stale",
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
		AcceptedGen:  func(_, _ string) (string, bool) { return "gen-1", true },
		Config:       CodeCallProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
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

type fakeCodeCallIntentStore struct {
	mu               sync.Mutex
	pendingByDomain  []SharedProjectionIntentRow
	pendingByRepoRun map[string][]SharedProjectionIntentRow
	marked           []string
	leaseGranted     bool
	claims           int
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

func (f *fakeCodeCallIntentStore) ListPendingRepoRunIntents(_ context.Context, repositoryID, sourceRunID, _ string, limit int) ([]SharedProjectionIntentRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	rows := make([]SharedProjectionIntentRow, 0, len(f.pendingByRepoRun[repositoryID+"|"+sourceRunID]))
	for _, row := range f.pendingByRepoRun[repositoryID+"|"+sourceRunID] {
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
