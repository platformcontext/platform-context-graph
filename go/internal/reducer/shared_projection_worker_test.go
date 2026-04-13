package reducer

import (
	"context"
	"testing"
	"time"
)

func TestLatestIntentsByRepoAndPartitionDeduplicates(t *testing.T) {
	t.Parallel()

	t0 := time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC)
	intents := []SharedProjectionIntentRow{
		{IntentID: "old-1", RepositoryID: "repo-a", PartitionKey: "pk-1", CreatedAt: t0},
		{IntentID: "new-1", RepositoryID: "repo-a", PartitionKey: "pk-1", CreatedAt: t0.Add(time.Second)},
		{IntentID: "only-1", RepositoryID: "repo-b", PartitionKey: "pk-2", CreatedAt: t0},
	}

	latest, superseded := LatestIntentsByRepoAndPartition(intents)
	if len(latest) != 2 {
		t.Fatalf("latest len = %d, want 2", len(latest))
	}
	if latest[0].IntentID != "new-1" {
		t.Errorf("latest[0].IntentID = %q, want new-1", latest[0].IntentID)
	}
	if latest[1].IntentID != "only-1" {
		t.Errorf("latest[1].IntentID = %q, want only-1", latest[1].IntentID)
	}
	if len(superseded) != 1 || superseded[0] != "old-1" {
		t.Errorf("superseded = %v, want [old-1]", superseded)
	}
}

func TestLatestIntentsByRepoAndPartitionEmpty(t *testing.T) {
	t.Parallel()

	latest, superseded := LatestIntentsByRepoAndPartition(nil)
	if latest != nil {
		t.Errorf("latest = %v, want nil", latest)
	}
	if superseded != nil {
		t.Errorf("superseded = %v, want nil", superseded)
	}
}

func TestLatestIntentsByRepoAndPartitionTripleSupersede(t *testing.T) {
	t.Parallel()

	t0 := time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC)
	intents := []SharedProjectionIntentRow{
		{IntentID: "v1", RepositoryID: "repo-a", PartitionKey: "pk-1", CreatedAt: t0},
		{IntentID: "v2", RepositoryID: "repo-a", PartitionKey: "pk-1", CreatedAt: t0.Add(time.Second)},
		{IntentID: "v3", RepositoryID: "repo-a", PartitionKey: "pk-1", CreatedAt: t0.Add(2 * time.Second)},
	}

	latest, superseded := LatestIntentsByRepoAndPartition(intents)
	if len(latest) != 1 || latest[0].IntentID != "v3" {
		t.Fatalf("latest = %v, want [v3]", latest)
	}
	if len(superseded) != 2 {
		t.Fatalf("superseded len = %d, want 2", len(superseded))
	}
}

func TestFilterAuthoritativeIntentsMatchesGeneration(t *testing.T) {
	t.Parallel()

	intents := []SharedProjectionIntentRow{
		{IntentID: "active-1", RepositoryID: "repo-a", SourceRunID: "run-1", GenerationID: "gen-1"},
		{IntentID: "stale-1", RepositoryID: "repo-a", SourceRunID: "run-2", GenerationID: "gen-old"},
		{IntentID: "active-2", RepositoryID: "repo-b", SourceRunID: "run-1", GenerationID: "gen-2"},
	}

	lookup := func(repoID, sourceRunID string) (string, bool) {
		accepted := map[string]map[string]string{
			"repo-a": {"run-1": "gen-1", "run-2": "gen-current"},
			"repo-b": {"run-1": "gen-2"},
		}
		if runs, ok := accepted[repoID]; ok {
			if gen, ok := runs[sourceRunID]; ok {
				return gen, true
			}
		}
		return "", false
	}

	active, staleIDs := FilterAuthoritativeIntents(intents, lookup)
	if len(active) != 2 {
		t.Fatalf("active len = %d, want 2", len(active))
	}
	if active[0].IntentID != "active-1" {
		t.Errorf("active[0] = %q, want active-1", active[0].IntentID)
	}
	if active[1].IntentID != "active-2" {
		t.Errorf("active[1] = %q, want active-2", active[1].IntentID)
	}
	if len(staleIDs) != 1 || staleIDs[0] != "stale-1" {
		t.Errorf("staleIDs = %v, want [stale-1]", staleIDs)
	}
}

func TestFilterAuthoritativeIntentsSkipsUnknownRepos(t *testing.T) {
	t.Parallel()

	intents := []SharedProjectionIntentRow{
		{IntentID: "unknown-1", RepositoryID: "repo-x", SourceRunID: "run-1", GenerationID: "gen-1"},
	}

	lookup := func(_, _ string) (string, bool) {
		return "", false
	}

	active, staleIDs := FilterAuthoritativeIntents(intents, lookup)
	if len(active) != 0 {
		t.Errorf("active = %v, want empty", active)
	}
	if len(staleIDs) != 0 {
		t.Errorf("staleIDs = %v, want empty", staleIDs)
	}
}

func TestFilterUpsertRows(t *testing.T) {
	t.Parallel()

	rows := []SharedProjectionIntentRow{
		{IntentID: "upsert-1", Payload: map[string]any{"action": "upsert"}},
		{IntentID: "delete-1", Payload: map[string]any{"action": "delete"}},
		{IntentID: "implicit-1", Payload: map[string]any{"platform_id": "p1"}},
		{IntentID: "nil-payload"},
	}

	result := filterUpsertRows(rows)
	if len(result) != 3 {
		t.Fatalf("filterUpsertRows len = %d, want 3", len(result))
	}
	if result[0].IntentID != "upsert-1" {
		t.Errorf("result[0] = %q", result[0].IntentID)
	}
	if result[1].IntentID != "implicit-1" {
		t.Errorf("result[1] = %q", result[1].IntentID)
	}
	if result[2].IntentID != "nil-payload" {
		t.Errorf("result[2] = %q", result[2].IntentID)
	}
}

func TestSelectPartitionBatchReturnsAcceptedBatch(t *testing.T) {
	t.Parallel()

	t0 := time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC)
	reader := &stubSharedIntentReader{
		pending: []SharedProjectionIntentRow{
			{IntentID: "i1", ProjectionDomain: "platform_infra", PartitionKey: "pk-a", RepositoryID: "repo-a", SourceRunID: "run-1", GenerationID: "gen-1", CreatedAt: t0},
			{IntentID: "i2", ProjectionDomain: "platform_infra", PartitionKey: "pk-b", RepositoryID: "repo-b", SourceRunID: "run-1", GenerationID: "gen-1", CreatedAt: t0},
		},
	}

	lookup := func(_, _ string) (string, bool) {
		return "gen-1", true
	}

	batch, err := SelectPartitionBatch(
		context.Background(), reader, "platform_infra",
		0, 1, // partition 0 of 1 → all rows match
		10, lookup,
	)
	if err != nil {
		t.Fatalf("SelectPartitionBatch error = %v", err)
	}
	if len(batch.LatestRows) != 2 {
		t.Fatalf("LatestRows len = %d, want 2", len(batch.LatestRows))
	}
}

func TestSelectPartitionBatchFiltersStale(t *testing.T) {
	t.Parallel()

	t0 := time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC)
	reader := &stubSharedIntentReader{
		pending: []SharedProjectionIntentRow{
			{IntentID: "active-1", ProjectionDomain: "platform_infra", PartitionKey: "pk-a", RepositoryID: "repo-a", SourceRunID: "run-1", GenerationID: "gen-current", CreatedAt: t0},
			{IntentID: "stale-1", ProjectionDomain: "platform_infra", PartitionKey: "pk-b", RepositoryID: "repo-a", SourceRunID: "run-1", GenerationID: "gen-old", CreatedAt: t0},
		},
	}

	lookup := func(_, _ string) (string, bool) {
		return "gen-current", true
	}

	batch, err := SelectPartitionBatch(
		context.Background(), reader, "platform_infra",
		0, 1, 10, lookup,
	)
	if err != nil {
		t.Fatalf("SelectPartitionBatch error = %v", err)
	}
	if len(batch.LatestRows) != 1 {
		t.Fatalf("LatestRows len = %d, want 1", len(batch.LatestRows))
	}
	if batch.LatestRows[0].IntentID != "active-1" {
		t.Errorf("LatestRows[0].IntentID = %q, want active-1", batch.LatestRows[0].IntentID)
	}
	if len(batch.StaleIDs) != 1 || batch.StaleIDs[0] != "stale-1" {
		t.Errorf("StaleIDs = %v, want [stale-1]", batch.StaleIDs)
	}
}

func TestProcessPartitionOnceFullCycle(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 13, 14, 0, 0, 0, time.UTC)
	t0 := now.Add(-time.Minute)

	reader := &stubSharedIntentReader{
		pending: []SharedProjectionIntentRow{
			{
				IntentID:         "intent-1",
				ProjectionDomain: "platform_infra",
				PartitionKey:     "pk-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{"platform_id": "p1", "action": "upsert"},
				CreatedAt:        t0,
			},
		},
	}

	lease := &stubLeaseManager{claimResult: true}
	edges := &stubEdgeWriter{}

	lookup := func(_, _ string) (string, bool) {
		return "gen-1", true
	}

	cfg := PartitionProcessorConfig{
		Domain:         "platform_infra",
		PartitionID:    0,
		PartitionCount: 1,
		LeaseOwner:     "worker-1",
		LeaseTTL:       30 * time.Second,
		BatchLimit:     100,
		EvidenceSource: "finalization/workloads",
	}

	result, err := ProcessPartitionOnce(context.Background(), now, cfg, lease, reader, edges, lookup)
	if err != nil {
		t.Fatalf("ProcessPartitionOnce error = %v", err)
	}
	if !result.LeaseAcquired {
		t.Fatal("LeaseAcquired = false, want true")
	}
	if result.ProcessedIntents != 1 {
		t.Errorf("ProcessedIntents = %d, want 1", result.ProcessedIntents)
	}
	if result.UpsertedRows != 1 {
		t.Errorf("UpsertedRows = %d, want 1", result.UpsertedRows)
	}
	if result.RetractedRows != 1 {
		t.Errorf("RetractedRows = %d, want 1", result.RetractedRows)
	}
	if !lease.released {
		t.Error("lease was not released")
	}
	if len(reader.completedIDs) != 1 {
		t.Errorf("completedIDs = %v, want [intent-1]", reader.completedIDs)
	}
	if len(edges.retractCalls) != 1 {
		t.Errorf("retractCalls = %d, want 1", len(edges.retractCalls))
	}
	if len(edges.writeCalls) != 1 {
		t.Errorf("writeCalls = %d, want 1", len(edges.writeCalls))
	}
}

func TestProcessPartitionOnceLeaseNotAcquired(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 13, 14, 0, 0, 0, time.UTC)
	lease := &stubLeaseManager{claimResult: false}
	reader := &stubSharedIntentReader{}
	edges := &stubEdgeWriter{}
	lookup := func(_, _ string) (string, bool) { return "", false }

	cfg := PartitionProcessorConfig{
		Domain:         "platform_infra",
		PartitionID:    0,
		PartitionCount: 1,
		LeaseOwner:     "worker-1",
		LeaseTTL:       30 * time.Second,
	}

	result, err := ProcessPartitionOnce(context.Background(), now, cfg, lease, reader, edges, lookup)
	if err != nil {
		t.Fatalf("ProcessPartitionOnce error = %v", err)
	}
	if result.LeaseAcquired {
		t.Error("LeaseAcquired = true, want false")
	}
	if result.ProcessedIntents != 0 {
		t.Errorf("ProcessedIntents = %d, want 0", result.ProcessedIntents)
	}
}

func TestProcessPartitionOnceEmptyBatch(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 13, 14, 0, 0, 0, time.UTC)
	lease := &stubLeaseManager{claimResult: true}
	reader := &stubSharedIntentReader{pending: nil}
	edges := &stubEdgeWriter{}
	lookup := func(_, _ string) (string, bool) { return "gen-1", true }

	cfg := PartitionProcessorConfig{
		Domain:         "platform_infra",
		PartitionID:    0,
		PartitionCount: 1,
		LeaseOwner:     "worker-1",
		LeaseTTL:       30 * time.Second,
	}

	result, err := ProcessPartitionOnce(context.Background(), now, cfg, lease, reader, edges, lookup)
	if err != nil {
		t.Fatalf("error = %v", err)
	}
	if !result.LeaseAcquired {
		t.Error("LeaseAcquired = false")
	}
	if result.ProcessedIntents != 0 {
		t.Errorf("ProcessedIntents = %d", result.ProcessedIntents)
	}
	if !lease.released {
		t.Error("lease was not released on empty batch")
	}
}

func TestProcessPartitionOnceFiltersDeleteAction(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 13, 14, 0, 0, 0, time.UTC)
	t0 := now.Add(-time.Minute)

	reader := &stubSharedIntentReader{
		pending: []SharedProjectionIntentRow{
			{
				IntentID:         "upsert-1",
				ProjectionDomain: "platform_infra",
				PartitionKey:     "pk-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{"action": "upsert"},
				CreatedAt:        t0,
			},
			{
				IntentID:         "delete-1",
				ProjectionDomain: "platform_infra",
				PartitionKey:     "pk-b",
				RepositoryID:     "repo-b",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{"action": "delete"},
				CreatedAt:        t0,
			},
		},
	}

	lease := &stubLeaseManager{claimResult: true}
	edges := &stubEdgeWriter{}
	lookup := func(_, _ string) (string, bool) { return "gen-1", true }

	cfg := PartitionProcessorConfig{
		Domain:         "platform_infra",
		PartitionID:    0,
		PartitionCount: 1,
		LeaseOwner:     "worker-1",
		LeaseTTL:       30 * time.Second,
		BatchLimit:     100,
		EvidenceSource: "finalization/workloads",
	}

	result, err := ProcessPartitionOnce(context.Background(), now, cfg, lease, reader, edges, lookup)
	if err != nil {
		t.Fatalf("error = %v", err)
	}
	if result.UpsertedRows != 1 {
		t.Errorf("UpsertedRows = %d, want 1 (delete should be filtered)", result.UpsertedRows)
	}
	if result.RetractedRows != 2 {
		t.Errorf("RetractedRows = %d, want 2 (both get retracted)", result.RetractedRows)
	}
}

// --- Test stubs ---

type stubSharedIntentReader struct {
	pending      []SharedProjectionIntentRow
	completedIDs []string
}

func (s *stubSharedIntentReader) ListPendingDomainIntents(_ context.Context, _ string, _ int) ([]SharedProjectionIntentRow, error) {
	return s.pending, nil
}

func (s *stubSharedIntentReader) MarkIntentsCompleted(_ context.Context, intentIDs []string, _ time.Time) error {
	s.completedIDs = append(s.completedIDs, intentIDs...)
	return nil
}

type stubLeaseManager struct {
	claimResult bool
	released    bool
}

func (s *stubLeaseManager) ClaimPartitionLease(_ context.Context, _ string, _, _ int, _ string, _ time.Duration) (bool, error) {
	return s.claimResult, nil
}

func (s *stubLeaseManager) ReleasePartitionLease(_ context.Context, _ string, _, _ int, _ string) error {
	s.released = true
	return nil
}

type stubEdgeWriter struct {
	retractCalls [][]SharedProjectionIntentRow
	writeCalls   [][]SharedProjectionIntentRow
}

func (s *stubEdgeWriter) RetractEdges(_ context.Context, _ string, rows []SharedProjectionIntentRow, _ string) error {
	s.retractCalls = append(s.retractCalls, rows)
	return nil
}

func (s *stubEdgeWriter) WriteEdges(_ context.Context, _ string, rows []SharedProjectionIntentRow, _ string) error {
	s.writeCalls = append(s.writeCalls, rows)
	return nil
}
