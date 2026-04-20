package workflow

import (
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

func TestReconcileRunProgressPendingCollection(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 20, 18, 0, 0, 0, time.UTC)
	run, completeness, err := ReconcileRunProgress(RunProgressSnapshot{
		Run: Run{
			RunID:       "run-pending",
			TriggerKind: TriggerKindBootstrap,
			Status:      RunStatusCollectionPending,
			CreatedAt:   now.Add(-time.Minute),
			UpdatedAt:   now.Add(-time.Minute),
		},
		Collectors: []CollectorRunProgress{{
			CollectorKind:        scope.CollectorGit,
			TotalWorkItems:       2,
			PendingWorkItems:     2,
			PublishedPhaseCounts: map[PhasePublicationKey]int{},
		}},
	}, now)
	if err != nil {
		t.Fatalf("ReconcileRunProgress() error = %v, want nil", err)
	}
	if got, want := run.Status, RunStatusCollectionPending; got != want {
		t.Fatalf("run.Status = %q, want %q", got, want)
	}
	if got, want := len(completeness), 2; got != want {
		t.Fatalf("len(completeness) = %d, want %d", got, want)
	}
	for _, state := range completeness {
		if got, want := state.Status, CompletenessStatusPending; got != want {
			t.Fatalf("phase %q status = %q, want %q", state.PhaseName, got, want)
		}
	}
}

func TestReconcileRunProgressCollectionActive(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 20, 18, 5, 0, 0, time.UTC)
	run, _, err := ReconcileRunProgress(RunProgressSnapshot{
		Run: Run{
			RunID:       "run-active",
			TriggerKind: TriggerKindBootstrap,
			Status:      RunStatusCollectionPending,
			CreatedAt:   now.Add(-time.Minute),
			UpdatedAt:   now.Add(-time.Minute),
		},
		Collectors: []CollectorRunProgress{{
			CollectorKind:        scope.CollectorGit,
			TotalWorkItems:       3,
			PendingWorkItems:     1,
			ClaimedWorkItems:     1,
			CompletedWorkItems:   1,
			PublishedPhaseCounts: map[PhasePublicationKey]int{},
		}},
	}, now)
	if err != nil {
		t.Fatalf("ReconcileRunProgress() error = %v, want nil", err)
	}
	if got, want := run.Status, RunStatusCollectionActive; got != want {
		t.Fatalf("run.Status = %q, want %q", got, want)
	}
}

func TestReconcileRunProgressReducerConverging(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 20, 18, 10, 0, 0, time.UTC)
	run, completeness, err := ReconcileRunProgress(RunProgressSnapshot{
		Run: Run{
			RunID:       "run-converging",
			TriggerKind: TriggerKindBootstrap,
			Status:      RunStatusCollectionActive,
			CreatedAt:   now.Add(-time.Minute),
			UpdatedAt:   now.Add(-time.Minute),
		},
		Collectors: []CollectorRunProgress{{
			CollectorKind:      scope.CollectorGit,
			TotalWorkItems:     2,
			CompletedWorkItems: 2,
			PublishedPhaseCounts: map[PhasePublicationKey]int{
				{
					Keyspace:  reducer.GraphProjectionKeyspaceCodeEntitiesUID,
					PhaseName: reducer.GraphProjectionPhaseCanonicalNodesCommitted,
				}: 2,
			},
		}},
	}, now)
	if err != nil {
		t.Fatalf("ReconcileRunProgress() error = %v, want nil", err)
	}
	if got, want := run.Status, RunStatusReducerConverging; got != want {
		t.Fatalf("run.Status = %q, want %q", got, want)
	}
	if got, want := completeness[0].Status, CompletenessStatusReady; got != want {
		t.Fatalf("canonical phase status = %q, want %q", got, want)
	}
	if got, want := completeness[1].Status, CompletenessStatusPending; got != want {
		t.Fatalf("semantic phase status = %q, want %q", got, want)
	}
}

func TestReconcileRunProgressComplete(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 20, 18, 15, 0, 0, time.UTC)
	run, completeness, err := ReconcileRunProgress(RunProgressSnapshot{
		Run: Run{
			RunID:       "run-complete",
			TriggerKind: TriggerKindBootstrap,
			Status:      RunStatusReducerConverging,
			CreatedAt:   now.Add(-time.Minute),
			UpdatedAt:   now.Add(-time.Minute),
		},
		Collectors: []CollectorRunProgress{{
			CollectorKind:      scope.CollectorGit,
			TotalWorkItems:     1,
			CompletedWorkItems: 1,
			PublishedPhaseCounts: map[PhasePublicationKey]int{
				{
					Keyspace:  reducer.GraphProjectionKeyspaceCodeEntitiesUID,
					PhaseName: reducer.GraphProjectionPhaseCanonicalNodesCommitted,
				}: 1,
				{
					Keyspace:  reducer.GraphProjectionKeyspaceCodeEntitiesUID,
					PhaseName: reducer.GraphProjectionPhaseSemanticNodesCommitted,
				}: 1,
			},
		}},
	}, now)
	if err != nil {
		t.Fatalf("ReconcileRunProgress() error = %v, want nil", err)
	}
	if got, want := run.Status, RunStatusComplete; got != want {
		t.Fatalf("run.Status = %q, want %q", got, want)
	}
	if run.FinishedAt.IsZero() {
		t.Fatal("run.FinishedAt = zero, want non-zero")
	}
	for _, state := range completeness {
		if got, want := state.Status, CompletenessStatusReady; got != want {
			t.Fatalf("phase %q status = %q, want %q", state.PhaseName, got, want)
		}
	}
}

func TestReconcileRunProgressFailed(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 20, 18, 20, 0, 0, time.UTC)
	run, completeness, err := ReconcileRunProgress(RunProgressSnapshot{
		Run: Run{
			RunID:       "run-failed",
			TriggerKind: TriggerKindBootstrap,
			Status:      RunStatusCollectionActive,
			CreatedAt:   now.Add(-time.Minute),
			UpdatedAt:   now.Add(-time.Minute),
		},
		Collectors: []CollectorRunProgress{{
			CollectorKind:       scope.CollectorGit,
			TotalWorkItems:      2,
			CompletedWorkItems:  1,
			FailedTerminalItems: 1,
			PublishedPhaseCounts: map[PhasePublicationKey]int{
				{
					Keyspace:  reducer.GraphProjectionKeyspaceCodeEntitiesUID,
					PhaseName: reducer.GraphProjectionPhaseCanonicalNodesCommitted,
				}: 1,
			},
		}},
	}, now)
	if err != nil {
		t.Fatalf("ReconcileRunProgress() error = %v, want nil", err)
	}
	if got, want := run.Status, RunStatusFailed; got != want {
		t.Fatalf("run.Status = %q, want %q", got, want)
	}
	for _, state := range completeness {
		if got, want := state.Status, CompletenessStatusBlocked; got != want {
			t.Fatalf("phase %q status = %q, want %q", state.PhaseName, got, want)
		}
	}
}

func TestRequiredPhasesForCollectorIncludesMultiCollectorFamilies(t *testing.T) {
	t.Parallel()

	for _, collectorKind := range []scope.CollectorKind{
		scope.CollectorGit,
		scope.CollectorAWS,
		scope.CollectorTerraformState,
	} {
		requirements := RequiredPhasesForCollector(collectorKind)
		if got, want := len(requirements), 2; got != want {
			t.Fatalf("collector %q requirements = %d, want %d", collectorKind, got, want)
		}
		for _, requirement := range requirements {
			if got, want := requirement.Keyspace, reducer.GraphProjectionKeyspaceCodeEntitiesUID; got != want {
				t.Fatalf("collector %q keyspace = %q, want %q", collectorKind, got, want)
			}
		}
	}
}
