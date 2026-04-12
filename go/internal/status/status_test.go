package status_test

import (
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/status"
)

func TestBuildReportClassifiesProgressingQueue(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			ScopeCounts: []status.NamedCount{
				{Name: "active", Count: 3},
			},
			GenerationCounts: []status.NamedCount{
				{Name: "active", Count: 1},
				{Name: "completed", Count: 4},
			},
			Queue: status.QueueSnapshot{
				Total:                8,
				Outstanding:          4,
				Pending:              1,
				InFlight:             2,
				Retrying:             1,
				Succeeded:            4,
				OldestOutstandingAge: 2 * time.Minute,
			},
			StageCounts: []status.StageStatusCount{
				{Stage: "projector", Status: "running", Count: 1},
				{Stage: "projector", Status: "pending", Count: 1},
				{Stage: "reducer", Status: "claimed", Count: 1},
				{Stage: "reducer", Status: "retrying", Count: 1},
			},
			DomainBacklogs: []status.DomainBacklog{
				{
					Domain:      "repository",
					Outstanding: 3,
					Retrying:    1,
					OldestAge:   2 * time.Minute,
				},
			},
		},
		status.DefaultOptions(),
	)

	if report.Health.State != "progressing" {
		t.Fatalf("BuildReport().Health.State = %q, want %q", report.Health.State, "progressing")
	}
	if len(report.StageSummaries) != 2 {
		t.Fatalf("BuildReport().StageSummaries len = %d, want 2", len(report.StageSummaries))
	}
	if got := report.StageSummaries[0].Stage; got != "projector" {
		t.Fatalf("BuildReport().StageSummaries[0].Stage = %q, want %q", got, "projector")
	}
	if got := report.StageSummaries[0].Running; got != 1 {
		t.Fatalf("BuildReport().StageSummaries[0].Running = %d, want 1", got)
	}
	if got := report.StageSummaries[1].Claimed; got != 1 {
		t.Fatalf("BuildReport().StageSummaries[1].Claimed = %d, want 1", got)
	}
}

func TestBuildReportClassifiesStalledBacklog(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			Queue: status.QueueSnapshot{
				Outstanding:          5,
				Pending:              5,
				OldestOutstandingAge: 12 * time.Minute,
			},
			StageCounts: []status.StageStatusCount{
				{Stage: "projector", Status: "pending", Count: 5},
			},
		},
		status.Options{
			StallAfter:  10 * time.Minute,
			DomainLimit: 5,
		},
	)

	if report.Health.State != "stalled" {
		t.Fatalf("BuildReport().Health.State = %q, want %q", report.Health.State, "stalled")
	}
	if len(report.Health.Reasons) == 0 {
		t.Fatal("BuildReport().Health.Reasons = empty, want non-empty")
	}
	if !strings.Contains(report.Health.Reasons[0], "no in-flight work") {
		t.Fatalf("BuildReport().Health.Reasons[0] = %q, want substring %q", report.Health.Reasons[0], "no in-flight work")
	}
}

func TestBuildReportClassifiesDegradedFailures(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			GenerationCounts: []status.NamedCount{
				{Name: "failed", Count: 1},
			},
			Queue: status.QueueSnapshot{
				Failed: 2,
			},
		},
		status.DefaultOptions(),
	)

	if report.Health.State != "degraded" {
		t.Fatalf("BuildReport().Health.State = %q, want %q", report.Health.State, "degraded")
	}
	if !strings.Contains(strings.Join(report.Health.Reasons, " "), "failed") {
		t.Fatalf("BuildReport().Health.Reasons = %v, want mention of failures", report.Health.Reasons)
	}
}

func TestRenderTextIncludesOperatorSummary(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			ScopeCounts: []status.NamedCount{
				{Name: "active", Count: 3},
			},
			GenerationCounts: []status.NamedCount{
				{Name: "active", Count: 1},
				{Name: "completed", Count: 2},
			},
			Queue: status.QueueSnapshot{
				Outstanding:          3,
				InFlight:             1,
				Retrying:             1,
				OldestOutstandingAge: 90 * time.Second,
			},
			StageCounts: []status.StageStatusCount{
				{Stage: "projector", Status: "running", Count: 1},
				{Stage: "projector", Status: "retrying", Count: 1},
				{Stage: "reducer", Status: "pending", Count: 1},
			},
			DomainBacklogs: []status.DomainBacklog{
				{
					Domain:      "repository",
					Outstanding: 2,
					Retrying:    1,
					OldestAge:   90 * time.Second,
				},
			},
		},
		status.DefaultOptions(),
	)

	rendered := status.RenderText(report)
	for _, want := range []string{
		"Health: progressing",
		"Queue: outstanding=3 in_flight=1 retrying=1 failed=0 oldest=1m30s",
		"Scopes: active=3",
		"Generations: active=1 completed=2",
		"projector pending=0 claimed=0 running=1 retrying=1 succeeded=0 failed=0",
		"repository outstanding=2 retrying=1 failed=0 oldest=1m30s",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("RenderText() missing %q in output:\n%s", want, rendered)
		}
	}
}
