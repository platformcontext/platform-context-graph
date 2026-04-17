package reducer

import (
	"context"
	"log/slog"
	"sync"
	"testing"
	"time"

	metricnoop "go.opentelemetry.io/otel/metric/noop"
	"go.opentelemetry.io/otel/trace/noop"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

type fakeSharedIntentReader struct {
	mu      sync.Mutex
	intents []SharedProjectionIntentRow
	marked  []string
}

func (f *fakeSharedIntentReader) ListPendingDomainIntents(_ context.Context, domain string, limit int) ([]SharedProjectionIntentRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()

	var result []SharedProjectionIntentRow
	for _, row := range f.intents {
		if row.ProjectionDomain == domain && row.CompletedAt == nil {
			result = append(result, row)
			if len(result) >= limit {
				break
			}
		}
	}
	return result, nil
}

func (f *fakeSharedIntentReader) MarkIntentsCompleted(_ context.Context, intentIDs []string, completedAt time.Time) error {
	f.mu.Lock()
	defer f.mu.Unlock()

	f.marked = append(f.marked, intentIDs...)
	idSet := make(map[string]struct{}, len(intentIDs))
	for _, id := range intentIDs {
		idSet[id] = struct{}{}
	}
	for i := range f.intents {
		if _, ok := idSet[f.intents[i].IntentID]; ok {
			t := completedAt
			f.intents[i].CompletedAt = &t
		}
	}
	return nil
}

type fakeLeaseManager struct {
	mu      sync.Mutex
	claims  int
	granted bool
}

func (f *fakeLeaseManager) ClaimPartitionLease(_ context.Context, _ string, _, _ int, _ string, _ time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.claims++
	return f.granted, nil
}

func (f *fakeLeaseManager) ReleasePartitionLease(_ context.Context, _ string, _, _ int, _ string) error {
	return nil
}

type fakeEdgeWriter struct {
	mu        sync.Mutex
	writes    int
	retracts  int
	writeRows []SharedProjectionIntentRow
}

func (f *fakeEdgeWriter) WriteEdges(_ context.Context, _ string, rows []SharedProjectionIntentRow, _ string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.writes++
	f.writeRows = append(f.writeRows, rows...)
	return nil
}

func (f *fakeEdgeWriter) RetractEdges(_ context.Context, _ string, rows []SharedProjectionIntentRow, _ string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.retracts++
	return nil
}

func TestSharedProjectionRunnerConfigDefaults(t *testing.T) {
	t.Parallel()

	cfg := SharedProjectionRunnerConfig{}
	if got := cfg.partitionCount(); got != defaultPartitionCount {
		t.Fatalf("partitionCount() = %d, want %d", got, defaultPartitionCount)
	}
	if got := cfg.pollInterval(); got != defaultSharedPollInterval {
		t.Fatalf("pollInterval() = %v, want %v", got, defaultSharedPollInterval)
	}
	if got := cfg.leaseTTL(); got != defaultLeaseTTL {
		t.Fatalf("leaseTTL() = %v, want %v", got, defaultLeaseTTL)
	}
	if got := cfg.batchLimit(); got != defaultBatchLimit {
		t.Fatalf("batchLimit() = %d, want %d", got, defaultBatchLimit)
	}
}

func TestSharedProjectionRunnerStopsOnCancelledContext(t *testing.T) {
	t.Parallel()

	runner := SharedProjectionRunner{
		IntentReader: &fakeSharedIntentReader{},
		LeaseManager: &fakeLeaseManager{granted: false},
		EdgeWriter:   &fakeEdgeWriter{},
		AcceptedGen:  acceptedGenerationFixed("gen-1", true),
		Config: SharedProjectionRunnerConfig{
			PollInterval: 10 * time.Millisecond,
		},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := runner.Run(ctx)
	if err != nil {
		t.Fatalf("Run() error = %v, want nil on cancelled context", err)
	}
}

func TestSharedProjectionRunnerProcessesPendingIntents(t *testing.T) {
	t.Parallel()

	reader := &fakeSharedIntentReader{
		intents: []SharedProjectionIntentRow{
			{
				IntentID:         "intent-1",
				ProjectionDomain: DomainPlatformInfra,
				PartitionKey:     "platform:eks-prod",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{"action": "upsert", "repo_id": "repo-a", "platform_id": "p1"},
				CreatedAt:        time.Date(2026, 4, 13, 12, 0, 0, 0, time.UTC),
			},
		},
	}
	leaseManager := &fakeLeaseManager{granted: true}
	edgeWriter := &fakeEdgeWriter{}

	runner := SharedProjectionRunner{
		IntentReader: reader,
		LeaseManager: leaseManager,
		EdgeWriter:   edgeWriter,
		AcceptedGen:  acceptedGenerationFixed("gen-1", true),
		Config: SharedProjectionRunnerConfig{
			PartitionCount: 1,
			LeaseOwner:     "test-runner",
			PollInterval:   10 * time.Millisecond,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	_ = runner.Run(ctx)

	reader.mu.Lock()
	markedCount := len(reader.marked)
	reader.mu.Unlock()

	if markedCount == 0 {
		t.Fatal("expected at least one intent to be marked completed")
	}
}

func TestSharedProjectionRunnerIteratesAllDomains(t *testing.T) {
	t.Parallel()

	reader := &fakeSharedIntentReader{}
	leaseManager := &fakeLeaseManager{granted: false}
	edgeWriter := &fakeEdgeWriter{}

	runner := SharedProjectionRunner{
		IntentReader: reader,
		LeaseManager: leaseManager,
		EdgeWriter:   edgeWriter,
		AcceptedGen:  acceptedGenerationFixed("", false),
		Config: SharedProjectionRunnerConfig{
			PartitionCount: 2,
			PollInterval:   10 * time.Millisecond,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	_ = runner.Run(ctx)

	leaseManager.mu.Lock()
	claims := leaseManager.claims
	leaseManager.mu.Unlock()

	wantPerCycle := len(sharedProjectionDomains) * 2
	if claims < wantPerCycle {
		t.Fatalf("expected at least %d lease claims (%d domains * 2 partitions), got %d", wantPerCycle, len(sharedProjectionDomains), claims)
	}
}

func TestSharedProjectionRunnerValidation(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		runner SharedProjectionRunner
	}{
		{
			name:   "nil intent reader",
			runner: SharedProjectionRunner{LeaseManager: &fakeLeaseManager{}, EdgeWriter: &fakeEdgeWriter{}},
		},
		{
			name:   "nil lease manager",
			runner: SharedProjectionRunner{IntentReader: &fakeSharedIntentReader{}, EdgeWriter: &fakeEdgeWriter{}},
		},
		{
			name:   "nil edge writer",
			runner: SharedProjectionRunner{IntentReader: &fakeSharedIntentReader{}, LeaseManager: &fakeLeaseManager{}},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			err := tt.runner.Run(context.Background())
			if err == nil {
				t.Fatal("Run() error = nil, want validation error")
			}
		})
	}
}

func TestSharedProjectionRunnerBackoffOnEmptyCycles(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	var waits []time.Duration

	runner := SharedProjectionRunner{
		IntentReader: &fakeSharedIntentReader{},
		LeaseManager: &fakeLeaseManager{granted: false},
		EdgeWriter:   &fakeEdgeWriter{},
		AcceptedGen:  acceptedGenerationFixed("", false),
		Config: SharedProjectionRunnerConfig{
			PartitionCount: 1,
			PollInterval:   500 * time.Millisecond,
		},
		Wait: func(_ context.Context, d time.Duration) error {
			mu.Lock()
			waits = append(waits, d)
			mu.Unlock()
			if len(waits) >= 5 {
				return context.Canceled
			}
			return nil
		},
	}

	_ = runner.Run(context.Background())

	mu.Lock()
	defer mu.Unlock()

	// Expected backoff sequence with base=500ms, doubling up to 5s cap:
	// consecutiveEmpty=1 → 500ms (no doubling)
	// consecutiveEmpty=2 → 1s (1 double)
	// consecutiveEmpty=3 → 2s (2 doubles)
	// consecutiveEmpty=4 → 4s (3 doubles, capped at i<4)
	// consecutiveEmpty=5 → 4s (still 3 doubles, i<4 cap)
	// consecutiveEmpty with higher base would hit the 5s maxSharedPollInterval cap.
	expected := []time.Duration{
		500 * time.Millisecond,
		1 * time.Second,
		2 * time.Second,
		4 * time.Second,
		4 * time.Second,
	}
	if len(waits) < len(expected) {
		t.Fatalf("wait calls = %d, want at least %d", len(waits), len(expected))
	}
	for i, want := range expected {
		if waits[i] != want {
			t.Errorf("wait[%d] = %v, want %v", i, waits[i], want)
		}
	}
}

func TestSharedProjectionRunnerBackoffResetsOnWork(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	var waits []time.Duration
	waitCount := 0

	reader := &fakeSharedIntentReader{}
	leaseManager := &fakeLeaseManager{granted: true}

	runner := SharedProjectionRunner{
		IntentReader: reader,
		LeaseManager: leaseManager,
		EdgeWriter:   &fakeEdgeWriter{},
		AcceptedGen:  acceptedGenerationFixed("gen-1", true),
		Config: SharedProjectionRunnerConfig{
			PartitionCount: 1,
			PollInterval:   500 * time.Millisecond,
		},
		Wait: func(_ context.Context, d time.Duration) error {
			mu.Lock()
			waits = append(waits, d)
			waitCount++
			wc := waitCount
			mu.Unlock()

			// After 2 empty waits, inject work so backoff resets.
			if wc == 2 {
				reader.mu.Lock()
				reader.intents = append(reader.intents, SharedProjectionIntentRow{
					IntentID:         "intent-reset",
					ProjectionDomain: DomainPlatformInfra,
					PartitionKey:     "platform:test",
					ScopeID:          "scope-b",
					AcceptanceUnitID: "repo-b",
					RepositoryID:     "repo-b",
					SourceRunID:      "run-1",
					GenerationID:     "gen-1",
					Payload:          map[string]any{"action": "upsert", "repo_id": "repo-b", "platform_id": "p2"},
					CreatedAt:        time.Date(2026, 4, 13, 12, 0, 0, 0, time.UTC),
				})
				reader.mu.Unlock()
			}
			// Stop after enough waits to see the reset.
			if wc >= 4 {
				return context.Canceled
			}
			return nil
		},
	}

	_ = runner.Run(context.Background())

	mu.Lock()
	defer mu.Unlock()

	// First two waits should show increasing backoff: 500ms, 1s.
	// After work resets, the next wait should be back to 500ms base.
	if len(waits) < 3 {
		t.Fatalf("wait calls = %d, want at least 3", len(waits))
	}
	if waits[0] != 500*time.Millisecond {
		t.Errorf("wait[0] = %v, want 500ms", waits[0])
	}
	if waits[1] != 1*time.Second {
		t.Errorf("wait[1] = %v, want 1s", waits[1])
	}
	// After work was done, backoff should reset. The next empty cycle
	// should wait at the base interval again.
	for i := 2; i < len(waits); i++ {
		if waits[i] == 500*time.Millisecond {
			return // found the reset — pass
		}
	}
	t.Errorf("backoff never reset to base interval after work; waits = %v", waits)
}

func TestSharedProjectionDomainsIncludesAllExpected(t *testing.T) {
	t.Parallel()

	expected := map[string]bool{
		DomainPlatformInfra:      false,
		DomainRepoDependency:     false,
		DomainWorkloadDependency: false,
		DomainInheritanceEdges:   false,
		DomainSQLRelationships:   false,
	}

	for _, domain := range sharedProjectionDomains {
		if _, ok := expected[domain]; !ok {
			t.Errorf("unexpected domain in sharedProjectionDomains: %q", domain)
		}
		expected[domain] = true
	}

	for domain, found := range expected {
		if !found {
			t.Errorf("expected domain %q not found in sharedProjectionDomains", domain)
		}
	}

	if got, want := len(sharedProjectionDomains), len(expected); got != want {
		t.Errorf("sharedProjectionDomains length = %d, want %d", got, want)
	}
}

func TestSharedProjectionRunnerProcessesNewDomainIntents(t *testing.T) {
	t.Parallel()

	reader := &fakeSharedIntentReader{
		intents: []SharedProjectionIntentRow{
			{
				IntentID:         "intent-inh-1",
				ProjectionDomain: DomainInheritanceEdges,
				PartitionKey:     "child->parent",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload: map[string]any{
					"action":            "upsert",
					"child_entity_id":   "entity:class:child",
					"parent_entity_id":  "entity:class:parent",
					"repo_id":           "repo-a",
					"relationship_type": "INHERITS",
				},
				CreatedAt: time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC),
			},
			{
				IntentID:         "intent-sql-1",
				ProjectionDomain: DomainSQLRelationships,
				PartitionKey:     "view->table",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload: map[string]any{
					"action":            "upsert",
					"source_entity_id":  "entity:sql_view:v1",
					"target_entity_id":  "entity:sql_table:t1",
					"repo_id":           "repo-a",
					"relationship_type": "REFERENCES_TABLE",
				},
				CreatedAt: time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC),
			},
		},
	}
	leaseManager := &fakeLeaseManager{granted: true}
	edgeWriter := &fakeEdgeWriter{}

	runner := SharedProjectionRunner{
		IntentReader: reader,
		LeaseManager: leaseManager,
		EdgeWriter:   edgeWriter,
		AcceptedGen:  acceptedGenerationFixed("gen-1", true),
		Config: SharedProjectionRunnerConfig{
			PartitionCount: 1,
			LeaseOwner:     "test-runner",
			PollInterval:   10 * time.Millisecond,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	_ = runner.Run(ctx)

	reader.mu.Lock()
	markedCount := len(reader.marked)
	reader.mu.Unlock()

	if markedCount < 2 {
		t.Fatalf("expected at least 2 intents marked completed, got %d", markedCount)
	}
}

func TestSharedProjectionRunnerWithTelemetry(t *testing.T) {
	t.Parallel()

	reader := &fakeSharedIntentReader{
		intents: []SharedProjectionIntentRow{
			{
				IntentID:         "intent-1",
				ProjectionDomain: DomainPlatformInfra,
				PartitionKey:     "platform:eks-prod",
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{"action": "upsert", "repo_id": "repo-a", "platform_id": "p1"},
				CreatedAt:        time.Date(2026, 4, 13, 12, 0, 0, 0, time.UTC),
			},
		},
	}
	leaseManager := &fakeLeaseManager{granted: true}
	edgeWriter := &fakeEdgeWriter{}

	tracer := noop.NewTracerProvider().Tracer("test")
	meter := metricnoop.NewMeterProvider().Meter("test")
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		t.Fatalf("NewInstruments() error = %v", err)
	}
	logger := slog.Default()

	runner := SharedProjectionRunner{
		IntentReader: reader,
		LeaseManager: leaseManager,
		EdgeWriter:   edgeWriter,
		AcceptedGen:  acceptedGenerationFixed("gen-1", true),
		Config: SharedProjectionRunnerConfig{
			PartitionCount: 1,
			LeaseOwner:     "test-runner",
			PollInterval:   10 * time.Millisecond,
		},
		Tracer:      tracer,
		Instruments: instruments,
		Logger:      logger,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	_ = runner.Run(ctx)

	reader.mu.Lock()
	markedCount := len(reader.marked)
	reader.mu.Unlock()

	if markedCount == 0 {
		t.Fatal("expected at least one intent to be marked completed")
	}
}
