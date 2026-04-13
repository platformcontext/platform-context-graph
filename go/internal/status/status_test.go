package status_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/status"
)

func TestLoadReportBuildsProjectionFromReader(t *testing.T) {
	t.Parallel()

	reader := &fakeReader{
		snapshot: status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			ScopeActivity: status.ScopeActivitySnapshot{
				Active:  2,
				Changed: 1,
			},
			GenerationCounts: []status.NamedCount{
				{Name: "active", Count: 2},
				{Name: "superseded", Count: 1},
			},
			Queue: status.QueueSnapshot{
				Outstanding:          2,
				InFlight:             1,
				OldestOutstandingAge: 30 * time.Second,
			},
		},
	}
	asOf := time.Date(2026, 4, 12, 12, 0, 0, 0, time.FixedZone("EDT", -4*60*60))

	report, err := status.LoadReport(context.Background(), reader, asOf, status.DefaultOptions())
	if err != nil {
		t.Fatalf("LoadReport() error = %v, want nil", err)
	}

	if got := reader.asOf; !got.Equal(asOf.UTC()) {
		t.Fatalf("LoadReport() reader asOf = %v, want %v", got, asOf.UTC())
	}
	if report.Health.State != "progressing" {
		t.Fatalf("LoadReport().Health.State = %q, want %q", report.Health.State, "progressing")
	}
	if report.AsOf != reader.snapshot.AsOf {
		t.Fatalf("LoadReport().AsOf = %v, want %v", report.AsOf, reader.snapshot.AsOf)
	}
}

func TestLoadReportRequiresReader(t *testing.T) {
	t.Parallel()

	_, err := status.LoadReport(
		context.Background(),
		nil,
		time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
		status.DefaultOptions(),
	)
	if err == nil {
		t.Fatal("LoadReport() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "reader is required") {
		t.Fatalf("LoadReport() error = %q, want mention of missing reader", err)
	}
}

func TestLoadReportPropagatesReaderErrors(t *testing.T) {
	t.Parallel()

	wantErr := errors.New("boom")
	reader := &fakeReader{err: wantErr}

	_, err := status.LoadReport(
		context.Background(),
		reader,
		time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
		status.DefaultOptions(),
	)
	if !errors.Is(err, wantErr) {
		t.Fatalf("LoadReport() error = %v, want wrapped %v", err, wantErr)
	}
}

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

type fakeReader struct {
	snapshot status.RawSnapshot
	err      error
	asOf     time.Time
}

func (r *fakeReader) ReadStatusSnapshot(_ context.Context, asOf time.Time) (status.RawSnapshot, error) {
	r.asOf = asOf
	if r.err != nil {
		return status.RawSnapshot{}, r.err
	}

	return r.snapshot, nil
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
			ScopeActivity: status.ScopeActivitySnapshot{
				Active:  2,
				Changed: 1,
			},
			ScopeCounts: []status.NamedCount{
				{Name: "active", Count: 3},
			},
			GenerationCounts: []status.NamedCount{
				{Name: "active", Count: 1},
				{Name: "completed", Count: 2},
				{Name: "superseded", Count: 1},
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
		"Scope activity: active=2 changed=1",
		"Scope statuses: active=3",
		"Generations: active=1 completed=2 superseded=1",
		"projector pending=0 claimed=0 running=1 retrying=1 succeeded=0 failed=0",
		"repository outstanding=2 retrying=1 failed=0 oldest=1m30s",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("RenderText() missing %q in output:\n%s", want, rendered)
		}
	}
}

func TestRenderTextDoesNotRepeatTopLevelSummaries(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			ScopeActivity: status.ScopeActivitySnapshot{
				Active:  4,
				Changed: 2,
			},
			ScopeCounts: []status.NamedCount{
				{Name: "active", Count: 2},
			},
			GenerationCounts: []status.NamedCount{
				{Name: "completed", Count: 3},
				{Name: "superseded", Count: 1},
			},
			Queue: status.QueueSnapshot{
				Outstanding:          1,
				InFlight:             1,
				OldestOutstandingAge: 30 * time.Second,
			},
		},
		status.DefaultOptions(),
	)

	rendered := status.RenderText(report)
	for _, want := range []string{
		"Queue: outstanding=1 in_flight=1 retrying=0 failed=0 oldest=30s overdue_claims=0",
		"Scope activity: active=4 changed=2",
		"Scope statuses: active=2",
		"Generations: completed=3 superseded=1",
	} {
		if got := strings.Count(rendered, want); got != 1 {
			t.Fatalf("RenderText() occurrences of %q = %d, want 1\n%s", want, got, rendered)
		}
	}
}

func TestBuildReportAddsFlowSummaries(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			ScopeActivity: status.ScopeActivitySnapshot{
				Active:  2,
				Changed: 1,
			},
			ScopeCounts: []status.NamedCount{
				{Name: "active", Count: 3},
				{Name: "pending", Count: 1},
			},
			GenerationCounts: []status.NamedCount{
				{Name: "active", Count: 1},
				{Name: "completed", Count: 4},
				{Name: "superseded", Count: 1},
			},
			StageCounts: []status.StageStatusCount{
				{Stage: "projector", Status: "running", Count: 2},
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

	if got := len(report.FlowSummaries); got != 3 {
		t.Fatalf("BuildReport().FlowSummaries len = %d, want 3", got)
	}
	if got := report.FlowSummaries[0]; got.Lane != "collector" || got.Source != "live" {
		t.Fatalf("BuildReport().FlowSummaries[0] = %+v, want collector/live", got)
	}
	if got := report.FlowSummaries[1]; got.Lane != "projector" || got.Source != "live" {
		t.Fatalf("BuildReport().FlowSummaries[1] = %+v, want projector/live", got)
	}
	if got := report.FlowSummaries[2]; got.Lane != "reducer" || got.Source != "live" {
		t.Fatalf("BuildReport().FlowSummaries[2] = %+v, want reducer/live", got)
	}
	if !strings.Contains(report.FlowSummaries[0].Progress, "scopes active=3 pending=1") {
		t.Fatalf("collector progress = %q, want scope totals", report.FlowSummaries[0].Progress)
	}
	if !strings.Contains(report.FlowSummaries[0].Backlog, "generations active=1 completed=4") {
		t.Fatalf("collector backlog = %q, want generation totals", report.FlowSummaries[0].Backlog)
	}
	if strings.Contains(report.FlowSummaries[0].Backlog, "not yet wired") {
		t.Fatalf("collector backlog = %q, want no placeholder wording", report.FlowSummaries[0].Backlog)
	}
	if !strings.Contains(report.FlowSummaries[1].Backlog, "queue") {
		t.Fatalf("projector backlog = %q, want queue pressure", report.FlowSummaries[1].Backlog)
	}
	if !strings.Contains(report.FlowSummaries[2].Backlog, "repository") {
		t.Fatalf("reducer backlog = %q, want top domain backlog", report.FlowSummaries[2].Backlog)
	}
}

func TestRenderJSONIncludesFlowSummaries(t *testing.T) {
	t.Parallel()

	report := status.BuildReport(
		status.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			Queue: status.QueueSnapshot{
				Outstanding: 1,
			},
			StageCounts: []status.StageStatusCount{
				{Stage: "projector", Status: "pending", Count: 1},
			},
		},
		status.DefaultOptions(),
	)

	payload, err := status.RenderJSON(report)
	if err != nil {
		t.Fatalf("RenderJSON() error = %v, want nil", err)
	}
	if !strings.Contains(string(payload), "\"flow\"") {
		t.Fatalf("RenderJSON() = %s, want flow summaries", payload)
	}
	if !strings.Contains(string(payload), "\"state\": \"progressing\"") {
		t.Fatalf("RenderJSON() = %s, want lower-case health state", payload)
	}
	if !strings.Contains(string(payload), "\"stage\": \"projector\"") {
		t.Fatalf("RenderJSON() = %s, want lower-case stage summary keys", payload)
	}
	if strings.Contains(string(payload), "\"State\"") {
		t.Fatalf("RenderJSON() = %s, want no exported-case health keys", payload)
	}
	if strings.Contains(string(payload), "\"Stage\"") {
		t.Fatalf("RenderJSON() = %s, want no exported-case stage keys", payload)
	}
}
