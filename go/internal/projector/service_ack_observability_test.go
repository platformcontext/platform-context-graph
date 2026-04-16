package projector

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"

	metricnoop "go.opentelemetry.io/otel/metric/noop"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestServiceRunLogsAckFailureWithQueueContext(t *testing.T) {
	t.Parallel()

	work := ScopeGenerationWork{
		Scope: scope.IngestionScope{
			ScopeID:       "scope-ack",
			SourceSystem:  "git",
			ScopeKind:     scope.KindRepository,
			CollectorKind: scope.CollectorGit,
			PartitionKey:  "repo-ack",
		},
		Generation: scope.ScopeGeneration{
			ScopeID:      "scope-ack",
			GenerationID: "generation-ack",
			ObservedAt:   time.Date(2026, time.April, 16, 10, 0, 0, 0, time.UTC),
			IngestedAt:   time.Date(2026, time.April, 16, 10, 0, 1, 0, time.UTC),
			Status:       scope.GenerationStatusPending,
			TriggerKind:  scope.TriggerKindSnapshot,
		},
	}

	var logs bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&logs, nil))
	instruments, err := telemetry.NewInstruments(metricnoop.NewMeterProvider().Meter("projector-ack"))
	if err != nil {
		t.Fatalf("NewInstruments() error = %v", err)
	}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubProjectorWorkSource{workItems: []ScopeGenerationWork{work}},
		FactStore: &stubFactStore{
			facts: []facts.Envelope{{
				FactID:       "fact-ack",
				ScopeID:      "scope-ack",
				GenerationID: "generation-ack",
				FactKind:     "source_node",
			}},
		},
		Runner: &stubProjectionRunner{
			result: Result{
				ScopeID:      "scope-ack",
				GenerationID: "generation-ack",
			},
		},
		WorkSink:    &stubProjectorWorkSink{ackErr: errors.New("ack store unavailable")},
		Wait:        func(context.Context, time.Duration) error { return context.Canceled },
		Logger:      logger,
		Instruments: instruments,
	}

	err = service.Run(context.Background())
	if err == nil {
		t.Fatal("Run() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "ack projector work") {
		t.Fatalf("Run() error = %v, want ack projector work", err)
	}

	sink := service.WorkSink.(*stubProjectorWorkSink)
	if got, want := sink.ackCalls, 1; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}

	logOutput := logs.String()
	for _, want := range []string{
		`"msg":"projection ack failed"`,
		`"failure_class":"ack_failure"`,
		`"queue":"projector"`,
		`"status":"ack_failed"`,
		`"scope_id":"scope-ack"`,
	} {
		if !strings.Contains(logOutput, want) {
			t.Fatalf("logs missing %s in %s", want, logOutput)
		}
	}
}
