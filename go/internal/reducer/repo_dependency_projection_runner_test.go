package reducer

import (
	"context"
	"errors"
	"sort"
	"sync"
	"testing"
	"time"
)

func TestRepoDependencyProjectionRunnerConfigDefaults(t *testing.T) {
	t.Parallel()

	cfg := RepoDependencyProjectionRunnerConfig{}
	if got := cfg.pollInterval(); got != defaultSharedPollInterval {
		t.Fatalf("pollInterval() = %v, want %v", got, defaultSharedPollInterval)
	}
	if got := cfg.leaseTTL(); got != defaultLeaseTTL {
		t.Fatalf("leaseTTL() = %v, want %v", got, defaultLeaseTTL)
	}
	if got := cfg.batchLimit(); got != defaultBatchLimit {
		t.Fatalf("batchLimit() = %d, want %d", got, defaultBatchLimit)
	}
	if got := cfg.leaseOwner(); got != defaultRepoDependencyLeaseOwner {
		t.Fatalf("leaseOwner() = %q, want %q", got, defaultRepoDependencyLeaseOwner)
	}
}

func TestRepoDependencyProjectionRunnerValidation(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		runner RepoDependencyProjectionRunner
	}{
		{
			name: "missing intent reader",
			runner: RepoDependencyProjectionRunner{
				LeaseManager: &fakeRepoDependencyIntentStore{leaseGranted: true},
				EdgeWriter:   &recordingCodeCallProjectionEdgeWriter{},
				AcceptedGen:  acceptedGenerationFixed("", false),
			},
		},
		{
			name: "missing lease manager",
			runner: RepoDependencyProjectionRunner{
				IntentReader: &fakeRepoDependencyIntentStore{leaseGranted: true},
				EdgeWriter:   &recordingCodeCallProjectionEdgeWriter{},
				AcceptedGen:  acceptedGenerationFixed("", false),
			},
		},
		{
			name: "missing edge writer",
			runner: RepoDependencyProjectionRunner{
				IntentReader: &fakeRepoDependencyIntentStore{leaseGranted: true},
				LeaseManager: &fakeRepoDependencyIntentStore{leaseGranted: true},
				AcceptedGen:  acceptedGenerationFixed("", false),
			},
		},
		{
			name: "missing accepted generation lookup",
			runner: RepoDependencyProjectionRunner{
				IntentReader: &fakeRepoDependencyIntentStore{leaseGranted: true},
				LeaseManager: &fakeRepoDependencyIntentStore{leaseGranted: true},
				EdgeWriter:   &recordingCodeCallProjectionEdgeWriter{},
			},
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

func TestRepoDependencyProjectionRunnerProcessesSourceRepoOwnedAcceptance(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 19, 12, 0, 0, 0, time.UTC)
	repoID := "repository:r_repo_a"
	reader := &fakeRepoDependencyIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			repoDependencyIntentRow(
				"stale-1", "scope-a", repoID, repoID, "run-1", "gen-old", now,
				map[string]any{
					"repo_id":           repoID,
					"target_repo_id":    "repository:r_old",
					"relationship_type": "DEPENDS_ON",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
			repoDependencyIntentRow(
				"active-1", "scope-b", repoID, repoID, "run-2", "gen-2", now.Add(time.Second),
				map[string]any{
					"repo_id":           repoID,
					"target_repo_id":    "repository:r_target_1",
					"relationship_type": "DEPENDS_ON",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
			repoDependencyIntentRow(
				"active-2", "scope-c", repoID, repoID, "run-3", "gen-3", now.Add(2*time.Second),
				map[string]any{
					"repo_id":           repoID,
					"target_repo_id":    "repository:r_target_2",
					"relationship_type": "DEPLOYS_FROM",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
			repoDependencyIntentRow(
				"other-1", "scope-d", "repository:r_repo_b", "repository:r_repo_b", "run-4", "gen-4", now.Add(3*time.Second),
				map[string]any{
					"repo_id":           "repository:r_repo_b",
					"target_repo_id":    "repository:r_target_3",
					"relationship_type": "DEPENDS_ON",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
		},
		pendingByAcceptanceUnit: map[string][]SharedProjectionIntentRow{
			repoID: {
				repoDependencyIntentRow(
					"stale-1", "scope-a", repoID, repoID, "run-1", "gen-old", now,
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_old",
						"relationship_type": "DEPENDS_ON",
						"evidence_source":   crossRepoEvidenceSource,
					},
				),
				repoDependencyIntentRow(
					"active-1", "scope-b", repoID, repoID, "run-2", "gen-2", now.Add(time.Second),
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_target_1",
						"relationship_type": "DEPENDS_ON",
						"evidence_source":   crossRepoEvidenceSource,
					},
				),
				repoDependencyIntentRow(
					"active-2", "scope-c", repoID, repoID, "run-3", "gen-3", now.Add(2*time.Second),
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_target_2",
						"relationship_type": "DEPLOYS_FROM",
						"evidence_source":   crossRepoEvidenceSource,
					},
				),
			},
		},
		leaseGranted: true,
	}
	writer := &recordingCodeCallProjectionEdgeWriter{}
	runner := RepoDependencyProjectionRunner{
		IntentReader: reader,
		LeaseManager: reader,
		EdgeWriter:   writer,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			switch {
			case key.ScopeID == "scope-a" && key.AcceptanceUnitID == repoID && key.SourceRunID == "run-1":
				return "gen-current", true
			case key.ScopeID == "scope-b" && key.AcceptanceUnitID == repoID && key.SourceRunID == "run-2":
				return "gen-2", true
			case key.ScopeID == "scope-c" && key.AcceptanceUnitID == repoID && key.SourceRunID == "run-3":
				return "gen-3", true
			default:
				return "", false
			}
		},
		Config: RepoDependencyProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
	}

	result, err := runner.processOnce(context.Background(), now)
	if err != nil {
		t.Fatalf("processOnce() error = %v", err)
	}
	if !result.LeaseAcquired {
		t.Fatal("LeaseAcquired = false, want true")
	}
	if result.ProcessedIntents != 3 {
		t.Fatalf("ProcessedIntents = %d, want 3", result.ProcessedIntents)
	}
	if len(writer.retractCalls) != 1 {
		t.Fatalf("len(retractCalls) = %d, want 1", len(writer.retractCalls))
	}
	if got, want := writer.retractCalls[0].evidenceSource, crossRepoEvidenceSource; got != want {
		t.Fatalf("retract evidenceSource = %q, want %q", got, want)
	}
	if len(writer.retractCalls[0].rows) != 1 {
		t.Fatalf("len(retractCalls[0].rows) = %d, want 1", len(writer.retractCalls[0].rows))
	}
	if got, want := writer.retractCalls[0].rows[0].RepositoryID, repoID; got != want {
		t.Fatalf("retract repo = %q, want %q", got, want)
	}
	if len(writer.writeCalls) != 1 {
		t.Fatalf("len(writeCalls) = %d, want 1", len(writer.writeCalls))
	}
	if len(writer.writeCalls[0].rows) != 2 {
		t.Fatalf("len(writeCalls[0].rows) = %d, want 2", len(writer.writeCalls[0].rows))
	}
	if len(reader.marked) != 3 {
		t.Fatalf("len(marked) = %d, want 3", len(reader.marked))
	}
	if got := reader.acceptanceUnitRequests; len(got) != 1 || got[0] != repoID {
		t.Fatalf("acceptanceUnitRequests = %v, want [%q]", got, repoID)
	}
}

func TestRepoDependencyProjectionRunnerRetractsPerEvidenceSourceAndSkipsRetractRowsOnWrite(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 19, 12, 30, 0, 0, time.UTC)
	repoID := "repository:r_repo_a"
	reader := &fakeRepoDependencyIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			repoDependencyIntentRow(
				"upsert-cross-repo", "scope-a", repoID, repoID, "run-1", "gen-1", now,
				map[string]any{
					"repo_id":           repoID,
					"target_repo_id":    "repository:r_target_1",
					"relationship_type": "DEPENDS_ON",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
		},
		pendingByAcceptanceUnit: map[string][]SharedProjectionIntentRow{
			repoID: {
				repoDependencyIntentRow(
					"upsert-cross-repo", "scope-a", repoID, repoID, "run-1", "gen-1", now,
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_target_1",
						"relationship_type": "DEPENDS_ON",
						"evidence_source":   crossRepoEvidenceSource,
					},
				),
				repoDependencyIntentRow(
					"retract-finalization", "scope-b", repoID, repoID, "run-2", "gen-2", now.Add(time.Second),
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_target_2",
						"relationship_type": "DEPENDS_ON",
						"evidence_source":   defaultEvidenceSource,
						"action":            "retract",
					},
				),
			},
		},
		leaseGranted: true,
	}
	writer := &recordingCodeCallProjectionEdgeWriter{}
	runner := RepoDependencyProjectionRunner{
		IntentReader: reader,
		LeaseManager: reader,
		EdgeWriter:   writer,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			switch key.SourceRunID {
			case "run-1":
				return "gen-1", true
			case "run-2":
				return "gen-2", true
			default:
				return "", false
			}
		},
		Config: RepoDependencyProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
	}

	_, err := runner.processOnce(context.Background(), now)
	if err != nil {
		t.Fatalf("processOnce() error = %v", err)
	}
	if len(writer.retractCalls) != 2 {
		t.Fatalf("len(retractCalls) = %d, want 2 evidence-source retracts", len(writer.retractCalls))
	}
	gotSources := []string{writer.retractCalls[0].evidenceSource, writer.retractCalls[1].evidenceSource}
	sort.Strings(gotSources)
	wantSources := []string{crossRepoEvidenceSource, defaultEvidenceSource}
	sort.Strings(wantSources)
	if got, want := gotSources, wantSources; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("retract sources = %v, want %v", gotSources, wantSources)
	}
	if len(writer.writeCalls) != 1 {
		t.Fatalf("len(writeCalls) = %d, want 1", len(writer.writeCalls))
	}
	if len(writer.writeCalls[0].rows) != 1 {
		t.Fatalf("len(writeCalls[0].rows) = %d, want 1 active upsert row", len(writer.writeCalls[0].rows))
	}
	if got, want := writer.writeCalls[0].rows[0].IntentID, "upsert-cross-repo"; got != want {
		t.Fatalf("written intent = %q, want %q", got, want)
	}
}

func TestRepoDependencyProjectionRunnerRehydratesCompletedContributorRows(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 19, 12, 45, 0, 0, time.UTC)
	repoID := "repository:r_repo_a"
	completedAt := now.Add(-time.Minute)
	completedContributor := repoDependencyIntentRow(
		"completed-1", "scope-old", repoID, repoID, "run-old", "gen-old", now.Add(-2*time.Minute),
		map[string]any{
			"repo_id":           repoID,
			"target_repo_id":    "repository:r_target_old",
			"relationship_type": "DEPENDS_ON",
			"evidence_source":   crossRepoEvidenceSource,
		},
	)
	completedContributor.CompletedAt = &completedAt

	reader := &fakeRepoDependencyIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			repoDependencyIntentRow(
				"pending-1", "scope-new", repoID, repoID, "run-new", "gen-new", now,
				map[string]any{
					"repo_id":           repoID,
					"target_repo_id":    "repository:r_target_new",
					"relationship_type": "DEPLOYS_FROM",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
		},
		pendingByAcceptanceUnit: map[string][]SharedProjectionIntentRow{
			repoID: {
				completedContributor,
				repoDependencyIntentRow(
					"pending-1", "scope-new", repoID, repoID, "run-new", "gen-new", now,
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_target_new",
						"relationship_type": "DEPLOYS_FROM",
						"evidence_source":   crossRepoEvidenceSource,
					},
				),
			},
		},
		leaseGranted: true,
	}
	writer := &recordingCodeCallProjectionEdgeWriter{}
	runner := RepoDependencyProjectionRunner{
		IntentReader: reader,
		LeaseManager: reader,
		EdgeWriter:   writer,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			switch key.SourceRunID {
			case "run-old":
				return "gen-old", true
			case "run-new":
				return "gen-new", true
			default:
				return "", false
			}
		},
		Config: RepoDependencyProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
	}

	_, err := runner.processOnce(context.Background(), now)
	if err != nil {
		t.Fatalf("processOnce() error = %v, want nil", err)
	}
	if len(writer.writeCalls) != 1 {
		t.Fatalf("len(writeCalls) = %d, want 1", len(writer.writeCalls))
	}
	if len(writer.writeCalls[0].rows) != 2 {
		t.Fatalf("len(writeCalls[0].rows) = %d, want 2 to preserve completed contributor", len(writer.writeCalls[0].rows))
	}
}

func TestRepoDependencyProjectionRunnerLoadAllAcceptanceUnitIntentsRejectsOversizedSlice(t *testing.T) {
	t.Parallel()

	reader := &fakeRepoDependencyIntentStore{
		acceptanceUnitResponder: func(_ string, limit int) ([]SharedProjectionIntentRow, error) {
			rows := make([]SharedProjectionIntentRow, limit)
			for i := range rows {
				rows[i] = repoDependencyIntentRow(
					"intent", "scope-a", "repository:r_repo_a", "repository:r_repo_a", "run-1", "gen-1", time.Now().UTC(),
					map[string]any{
						"repo_id":           "repository:r_repo_a",
						"target_repo_id":    "repository:r_target",
						"relationship_type": "DEPENDS_ON",
						"evidence_source":   crossRepoEvidenceSource,
					},
				)
			}
			return rows, nil
		},
	}
	runner := RepoDependencyProjectionRunner{
		IntentReader: reader,
		Config:       RepoDependencyProjectionRunnerConfig{BatchLimit: 100},
	}

	_, err := runner.loadAllAcceptanceUnitIntents(context.Background(), "repository:r_repo_a")
	if err == nil {
		t.Fatal("loadAllAcceptanceUnitIntents() error = nil, want non-nil")
	}
	if len(reader.acceptanceLimitRequests) < 2 {
		t.Fatalf("acceptanceLimitRequests = %v, want growth up to cap", reader.acceptanceLimitRequests)
	}
	if got, want := reader.acceptanceLimitRequests[len(reader.acceptanceLimitRequests)-1], maxRepoDependencyAcceptanceScanLimit; got != want {
		t.Fatalf("final acceptance scan limit = %d, want %d", got, want)
	}
}

type fakeRepoDependencyIntentStore struct {
	mu                        sync.Mutex
	pendingByDomain           []SharedProjectionIntentRow
	pendingByAcceptanceUnit   map[string][]SharedProjectionIntentRow
	marked                    []string
	leaseGranted              bool
	leaseClaims               int
	domainLimitRequests       []int
	acceptanceLimitRequests   []int
	acceptanceUnitRequests    []string
	acceptanceUnitResponder   func(acceptanceUnitID string, limit int) ([]SharedProjectionIntentRow, error)
	domainIntentListError     error
	acceptanceIntentListError error
}

func (f *fakeRepoDependencyIntentStore) ListPendingDomainIntents(_ context.Context, _ string, limit int) ([]SharedProjectionIntentRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	if f.domainIntentListError != nil {
		return nil, f.domainIntentListError
	}
	f.domainLimitRequests = append(f.domainLimitRequests, limit)
	return truncatePendingRows(f.pendingByDomain, limit), nil
}

func (f *fakeRepoDependencyIntentStore) ListAcceptanceUnitDomainIntents(_ context.Context, acceptanceUnitID, _ string, limit int) ([]SharedProjectionIntentRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	if f.acceptanceIntentListError != nil {
		return nil, f.acceptanceIntentListError
	}
	f.acceptanceLimitRequests = append(f.acceptanceLimitRequests, limit)
	f.acceptanceUnitRequests = append(f.acceptanceUnitRequests, acceptanceUnitID)
	if f.acceptanceUnitResponder != nil {
		return f.acceptanceUnitResponder(acceptanceUnitID, limit)
	}
	return truncateAcceptanceUnitRows(f.pendingByAcceptanceUnit[acceptanceUnitID], limit), nil
}

func (f *fakeRepoDependencyIntentStore) MarkIntentsCompleted(_ context.Context, intentIDs []string, _ time.Time) error {
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
	for key := range f.pendingByAcceptanceUnit {
		for i := range f.pendingByAcceptanceUnit[key] {
			if _, ok := markSet[f.pendingByAcceptanceUnit[key][i].IntentID]; ok {
				f.pendingByAcceptanceUnit[key][i].CompletedAt = &completedAt
			}
		}
	}
	return nil
}

func (f *fakeRepoDependencyIntentStore) ClaimPartitionLease(_ context.Context, _ string, _, _ int, _ string, _ time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.leaseClaims++
	return f.leaseGranted, nil
}

func (f *fakeRepoDependencyIntentStore) ReleasePartitionLease(_ context.Context, _ string, _, _ int, _ string) error {
	return nil
}

func truncatePendingRows(rows []SharedProjectionIntentRow, limit int) []SharedProjectionIntentRow {
	filtered := make([]SharedProjectionIntentRow, 0, len(rows))
	for _, row := range rows {
		if row.CompletedAt != nil {
			continue
		}
		filtered = append(filtered, row)
	}
	sort.SliceStable(filtered, func(i, j int) bool {
		if !filtered[i].CreatedAt.Equal(filtered[j].CreatedAt) {
			return filtered[i].CreatedAt.Before(filtered[j].CreatedAt)
		}
		return filtered[i].IntentID < filtered[j].IntentID
	})
	if limit > 0 && len(filtered) > limit {
		filtered = filtered[:limit]
	}
	return filtered
}

func truncateRowsForLimit(rows []SharedProjectionIntentRow, limit int) []SharedProjectionIntentRow {
	filtered := append([]SharedProjectionIntentRow(nil), rows...)
	sort.SliceStable(filtered, func(i, j int) bool {
		if !filtered[i].CreatedAt.Equal(filtered[j].CreatedAt) {
			return filtered[i].CreatedAt.Before(filtered[j].CreatedAt)
		}
		return filtered[i].IntentID < filtered[j].IntentID
	})
	if limit > 0 && len(filtered) > limit {
		filtered = filtered[:limit]
	}
	return filtered
}

func truncateAcceptanceUnitRows(rows []SharedProjectionIntentRow, limit int) []SharedProjectionIntentRow {
	return truncateRowsForLimit(rows, limit)
}

func repoDependencyIntentRow(
	intentID string,
	scopeID string,
	acceptanceUnitID string,
	repositoryID string,
	sourceRunID string,
	generationID string,
	createdAt time.Time,
	payload map[string]any,
) SharedProjectionIntentRow {
	return SharedProjectionIntentRow{
		IntentID:         intentID,
		ProjectionDomain: DomainRepoDependency,
		PartitionKey:     intentID,
		ScopeID:          scopeID,
		AcceptanceUnitID: acceptanceUnitID,
		RepositoryID:     repositoryID,
		SourceRunID:      sourceRunID,
		GenerationID:     generationID,
		Payload:          payload,
		CreatedAt:        createdAt,
	}
}

func TestRepoDependencyProjectionRunnerRunContinuesAfterCycleError(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 19, 13, 0, 0, 0, time.UTC)
	repoID := "repository:r_repo_a"
	reader := &fakeRepoDependencyIntentStore{
		pendingByDomain: []SharedProjectionIntentRow{
			repoDependencyIntentRow(
				"active-1", "scope-a", repoID, repoID, "run-1", "gen-1", now,
				map[string]any{
					"repo_id":           repoID,
					"target_repo_id":    "repository:r_target_1",
					"relationship_type": "DEPENDS_ON",
					"evidence_source":   crossRepoEvidenceSource,
				},
			),
		},
		pendingByAcceptanceUnit: map[string][]SharedProjectionIntentRow{
			repoID: {
				repoDependencyIntentRow(
					"active-1", "scope-a", repoID, repoID, "run-1", "gen-1", now,
					map[string]any{
						"repo_id":           repoID,
						"target_repo_id":    "repository:r_target_1",
						"relationship_type": "DEPENDS_ON",
						"evidence_source":   crossRepoEvidenceSource,
					},
				),
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

	runner := RepoDependencyProjectionRunner{
		IntentReader: reader,
		LeaseManager: reader,
		EdgeWriter:   writer,
		AcceptedGen: func(key SharedProjectionAcceptanceKey) (string, bool) {
			return "gen-1", key.AcceptanceUnitID == repoID
		},
		Config: RepoDependencyProjectionRunnerConfig{PollInterval: 10 * time.Millisecond},
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
		t.Fatalf("len(marked) = %d, want 1", got)
	}
	if got := len(writer.writeCalls); got != 1 {
		t.Fatalf("len(writeCalls) = %d, want 1", got)
	}
}
