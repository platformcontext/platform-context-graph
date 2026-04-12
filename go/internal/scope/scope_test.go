package scope

import (
	"testing"
	"time"
)

func TestIngestionScopeValidate(t *testing.T) {
	t.Parallel()

	got := IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     KindRepository,
		ParentScopeID: "parent-456",
		CollectorKind: CollectorGit,
		PartitionKey:  "repo-123",
		Metadata: map[string]string{
			"repository": "platform-context-graph",
		},
	}

	if err := got.Validate(); err != nil {
		t.Fatalf("Validate() error = %v, want nil", err)
	}
}

func TestIngestionScopeValidateRejectsBlankIdentifiers(t *testing.T) {
	t.Parallel()

	got := IngestionScope{
		SourceSystem:  "git",
		ScopeKind:     KindRepository,
		CollectorKind: CollectorGit,
		PartitionKey:  "repo-123",
	}

	if err := got.Validate(); err == nil {
		t.Fatal("Validate() error = nil, want non-nil")
	}
}

func TestIngestionScopeValidateRejectsBlankPartitionKey(t *testing.T) {
	t.Parallel()

	got := IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     KindRepository,
		CollectorKind: CollectorGit,
	}

	if err := got.Validate(); err == nil {
		t.Fatal("Validate() error = nil, want non-nil")
	}
}

func TestScopeGenerationValidate(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC)
	ingestedAt := observedAt.Add(5 * time.Minute)

	got := ScopeGeneration{
		GenerationID:  "generation-123",
		ScopeID:       "scope-123",
		ObservedAt:    observedAt,
		IngestedAt:    ingestedAt,
		Status:        GenerationStatusPending,
		TriggerKind:   TriggerKindSnapshot,
		FreshnessHint: "fresh",
	}

	if err := got.Validate(); err != nil {
		t.Fatalf("Validate() error = %v, want nil", err)
	}
}

func TestScopeGenerationValidateRejectsUnknownStatus(t *testing.T) {
	t.Parallel()

	got := ScopeGeneration{
		GenerationID: "generation-123",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       GenerationStatus("mystery"),
		TriggerKind:  TriggerKindSnapshot,
	}

	if err := got.Validate(); err == nil {
		t.Fatal("Validate() error = nil, want non-nil")
	}
}

func TestScopeGenerationValidateRejectsBackwardsTimestamps(t *testing.T) {
	t.Parallel()

	got := ScopeGeneration{
		GenerationID: "generation-123",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		Status:       GenerationStatusPending,
		TriggerKind:  TriggerKindSnapshot,
	}

	if err := got.Validate(); err == nil {
		t.Fatal("Validate() error = nil, want non-nil")
	}
}

func TestScopeGenerationTransitionTo(t *testing.T) {
	t.Parallel()

	base := ScopeGeneration{
		GenerationID: "generation-123",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       GenerationStatusPending,
		TriggerKind:  TriggerKindSnapshot,
	}

	activated, err := base.TransitionTo(GenerationStatusActive)
	if err != nil {
		t.Fatalf("TransitionTo(active) error = %v, want nil", err)
	}

	if activated.Status != GenerationStatusActive {
		t.Fatalf("Status = %q, want %q", activated.Status, GenerationStatusActive)
	}

	completed, err := activated.TransitionTo(GenerationStatusCompleted)
	if err != nil {
		t.Fatalf("TransitionTo(completed) error = %v, want nil", err)
	}

	if completed.Status != GenerationStatusCompleted {
		t.Fatalf("Status = %q, want %q", completed.Status, GenerationStatusCompleted)
	}
}

func TestScopeGenerationTransitionRejectsTerminalToActive(t *testing.T) {
	t.Parallel()

	base := ScopeGeneration{
		GenerationID: "generation-123",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       GenerationStatusCompleted,
		TriggerKind:  TriggerKindSnapshot,
	}

	if _, err := base.TransitionTo(GenerationStatusActive); err == nil {
		t.Fatal("TransitionTo(active) error = nil, want non-nil")
	}
}

func TestScopeGenerationValidateForScope(t *testing.T) {
	t.Parallel()

	scope := IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     KindRepository,
		CollectorKind: CollectorGit,
		PartitionKey:  "repo-123",
	}
	generation := ScopeGeneration{
		GenerationID: "generation-123",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       GenerationStatusPending,
		TriggerKind:  TriggerKindSnapshot,
	}

	if err := generation.ValidateForScope(scope); err != nil {
		t.Fatalf("ValidateForScope() error = %v, want nil", err)
	}
}

func TestScopeGenerationValidateForScopeRejectsMismatch(t *testing.T) {
	t.Parallel()

	scope := IngestionScope{
		ScopeID:       "scope-999",
		SourceSystem:  "git",
		ScopeKind:     KindRepository,
		CollectorKind: CollectorGit,
		PartitionKey:  "repo-123",
	}
	generation := ScopeGeneration{
		GenerationID: "generation-123",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
		IngestedAt:   time.Date(2026, time.April, 12, 11, 35, 0, 0, time.UTC),
		Status:       GenerationStatusPending,
		TriggerKind:  TriggerKindSnapshot,
	}

	if err := generation.ValidateForScope(scope); err == nil {
		t.Fatal("ValidateForScope() error = nil, want non-nil")
	}
}
