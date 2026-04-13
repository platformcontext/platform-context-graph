package reducer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const defaultPollInterval = time.Second

// WorkSource claims one reducer intent at a time.
type WorkSource interface {
	Claim(context.Context) (Intent, bool, error)
}

// Executor executes one claimed reducer intent.
type Executor interface {
	Execute(context.Context, Intent) (Result, error)
}

// WorkSink acknowledges or fails one claimed reducer intent.
type WorkSink interface {
	Ack(context.Context, Intent, Result) error
	Fail(context.Context, Intent, error) error
}

// Service coordinates reducer polling and one-intent-at-a-time execution.
type Service struct {
	PollInterval time.Duration
	WorkSource   WorkSource
	Executor     Executor
	WorkSink     WorkSink
	Wait         func(context.Context, time.Duration) error

	// SharedProjectionEdgeWriter is the Neo4j edge writer used by the shared
	// projection worker loop (ProcessPartitionOnce). Nil until Neo4j is wired.
	SharedProjectionEdgeWriter SharedProjectionEdgeWriter

	// SharedProjectionRunner runs the shared projection intent processing loop
	// concurrently with the main claim/execute/ack loop. Nil disables the runner.
	SharedProjectionRunner *SharedProjectionRunner

	// Telemetry fields (optional)
	Tracer      trace.Tracer
	Instruments *telemetry.Instruments
	Logger      *slog.Logger
}

// Run polls for reducer work until the context is canceled. If a
// SharedProjectionRunner is configured, it runs concurrently as a goroutine.
func (s Service) Run(ctx context.Context) error {
	if err := s.validate(); err != nil {
		return err
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	var wg sync.WaitGroup
	var runnerErr error

	if s.SharedProjectionRunner != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := s.SharedProjectionRunner.Run(ctx); err != nil {
				runnerErr = err
				cancel()
			}
		}()
	}

	err := s.runMainLoop(ctx)

	cancel()
	wg.Wait()

	if err != nil {
		return err
	}
	return runnerErr
}

// runMainLoop is the main claim/execute/ack loop extracted for concurrent use.
func (s Service) runMainLoop(ctx context.Context) error {
	for {
		intent, ok, err := s.WorkSource.Claim(ctx)
		if err != nil {
			return fmt.Errorf("claim reducer work: %w", err)
		}
		if !ok {
			if err := s.wait(ctx, s.pollInterval()); err != nil {
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("wait for reducer work: %w", err)
			}
			continue
		}

		if err := s.executeWithTelemetry(ctx, intent); err != nil {
			return err
		}
	}
}

func (s Service) validate() error {
	if s.WorkSource == nil {
		return errors.New("work source is required")
	}
	if s.Executor == nil {
		return errors.New("executor is required")
	}
	if s.WorkSink == nil {
		return errors.New("work sink is required")
	}

	return nil
}

func (s Service) pollInterval() time.Duration {
	if s.PollInterval <= 0 {
		return defaultPollInterval
	}

	return s.PollInterval
}

func (s Service) wait(ctx context.Context, interval time.Duration) error {
	if s.Wait != nil {
		return s.Wait(ctx, interval)
	}

	timer := time.NewTimer(interval)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func (s Service) executeWithTelemetry(ctx context.Context, intent Intent) error {
	start := time.Now()

	if s.Tracer != nil {
		var span trace.Span
		ctx, span = s.Tracer.Start(ctx, telemetry.SpanReducerRun)
		defer span.End()
	}

	result, err := s.Executor.Execute(ctx, intent)
	duration := time.Since(start).Seconds()
	status := "succeeded"

	if err != nil {
		status = "failed"
		s.recordReducerResult(ctx, intent, duration, status)
		if failErr := s.WorkSink.Fail(ctx, intent, err); failErr != nil {
			return errors.Join(err, fmt.Errorf("fail reducer work: %w", failErr))
		}
		return nil
	}

	if err := s.WorkSink.Ack(ctx, intent, result); err != nil {
		return fmt.Errorf("ack reducer work: %w", err)
	}

	s.recordReducerResult(ctx, intent, duration, status)
	return nil
}

func (s Service) recordReducerResult(ctx context.Context, intent Intent, duration float64, status string) {
	if s.Instruments != nil {
		attrs := metric.WithAttributes(
			telemetry.AttrDomain(string(intent.Domain)),
			attribute.String("status", status),
		)
		s.Instruments.ReducerRunDuration.Record(ctx, duration, metric.WithAttributes(
			telemetry.AttrDomain(string(intent.Domain)),
		))
		s.Instruments.ReducerExecutions.Add(ctx, 1, attrs)
	}

	if s.Logger != nil {
		partitionKey := ""
		if len(intent.EntityKeys) > 0 {
			partitionKey = intent.EntityKeys[0]
		}
		domainAttrs := telemetry.DomainAttrs(string(intent.Domain), partitionKey)
		logAttrs := make([]any, 0, len(domainAttrs)+3)
		for _, a := range domainAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs, slog.String("intent_id", intent.IntentID))
		logAttrs = append(logAttrs, slog.String("status", status))
		logAttrs = append(logAttrs, slog.Float64("duration_seconds", duration))
		logAttrs = append(logAttrs, telemetry.PhaseAttr(telemetry.PhaseReduction))
		if status == "failed" {
			logAttrs = append(logAttrs, telemetry.FailureClassAttr("reducer_failure"))
			s.Logger.ErrorContext(ctx, "reducer execution failed", logAttrs...)
		} else {
			s.Logger.InfoContext(ctx, "reducer execution succeeded", logAttrs...)
		}
	}
}
