package reducer

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"

	metricnoop "go.opentelemetry.io/otel/metric/noop"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestServiceRunLogsAckFailureWithQueueContext(t *testing.T) {
	t.Parallel()

	intent := Intent{
		IntentID:        "intent-ack",
		ScopeID:         "scope-ack",
		GenerationID:    "generation-ack",
		SourceSystem:    "git",
		Domain:          DomainRepoDependency,
		Cause:           "typed relationship follow-up",
		EntityKeys:      []string{"repo:platform-context-graph"},
		RelatedScopeIDs: []string{"scope-related"},
		EnqueuedAt:      time.Date(2026, time.April, 16, 11, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 16, 11, 0, 0, 0, time.UTC),
		Status:          IntentStatusPending,
	}

	var logs bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&logs, nil))
	instruments, err := telemetry.NewInstruments(metricnoop.NewMeterProvider().Meter("reducer-ack"))
	if err != nil {
		t.Fatalf("NewInstruments() error = %v", err)
	}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubReducerWorkSource{intents: []Intent{intent}},
		Executor: &stubReducerExecutor{
			result: Result{
				IntentID: intent.IntentID,
				Domain:   intent.Domain,
				Status:   ResultStatusSucceeded,
			},
		},
		WorkSink:    &stubReducerWorkSink{ackErr: errors.New("ack lease update failed")},
		Wait:        func(context.Context, time.Duration) error { return context.Canceled },
		Logger:      logger,
		Instruments: instruments,
	}

	err = service.Run(context.Background())
	if err == nil {
		t.Fatal("Run() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "ack reducer work") {
		t.Fatalf("Run() error = %v, want ack reducer work", err)
	}

	sink := service.WorkSink.(*stubReducerWorkSink)
	if got, want := sink.ackCalls, 1; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}

	logOutput := logs.String()
	for _, want := range []string{
		`"msg":"reducer ack failed"`,
		`"failure_class":"ack_failure"`,
		`"queue":"reducer"`,
		`"status":"ack_failed"`,
		`"intent_id":"intent-ack"`,
	} {
		if !strings.Contains(logOutput, want) {
			t.Fatalf("logs missing %s in %s", want, logOutput)
		}
	}
}
